# Extension 机制设计文档 v0.0.6.3
## 宽容路由 + 热加载 + 回扫

---

## 1. 概览

Extension 是扩展 zchat 行为的普遍模式。去掉某个 Extension 后 zchat 仍然是 zchat——Extension 改变的是某种行为语义（如消息投递可靠性、Agent 所有权转移），而非 zchat 的核心概念。

当前已设计的 Extension：
- `ext-migrate` — grant/reclaim，改变 Agent 所有权语义
- `ext-offline` — outbox/relay/inbox，改变消息投递的可靠性语义

未来可能的 Extension：
- `ext-socialware` — 组织活动 DAG 的 View 层
- `ext-channel-bridge` — 飞书/Telegram/Discord 消息桥接

---

## 2. 设计原则

```
1. 宽容路由：core 透传所有结构合法的 ZChatEvent，不管 content_type 是否已知
2. 宽容存储：所有 event 正常存入 Event Store，不因类型未知而丢弃
3. 全部 local：extension 只管理本机行为，不做跨 peer 协商
4. 人类兜底：对端缺少 extension 时提示安装，由人类沟通解决
5. 显式热加载：zchat ext install/uninstall 触发，daemon 不重启
6. 回扫闭环：热加载后回扫 Event Store 中近期未处理的相关 event
7. 命名约定：ContentType 使用 MIME 格式（wire），short name（人类交互）。Extension 的 short name 前缀为 ext.{name}.*
8. 扁平依赖：简单列表，不做版本范围解析
```

---

## 3. Manifest 格式

Extension 通过 `extension.toml` 声明自己注册的所有挂载点。

```toml
# extension.toml

[extension]
name = "migrate"
version = "0.1.0"
description = "Agent ownership transfer between peers"
requires_core = ">=0.0.6"

[content_types]
register = [
  { short = "ext.migrate.migration-bundle", schema = "schemas/migration-bundle.json" },
  { short = "ext.migrate.session-end-bundle", schema = "schemas/session-end-bundle.json" },
]

[hooks]
register = [
  { trigger = "on_migrate_out", handler = "migrate:bundle_pack",    runtime = "zchat", priority = 10 },
  { trigger = "on_migrate_in",  handler = "migrate:bundle_restore", runtime = "zchat", priority = 10 },
]

[indexes]
register = [
  { pattern = "zchat/acp/{session}/migrate", queryable = true, retention = "jsonl" },
  { pattern = "zchat/acp/{session}/history", queryable = true, retention = "jsonl" },
]

[annotations]
keys = []

[operations]
register = []

[cli]
subcommands = [
  { path = "session grant",   entry_point = "zchat_ext_migrate.cli:grant_cmd" },
  { path = "session reclaim", entry_point = "zchat_ext_migrate.cli:reclaim_cmd" },
]

[dependencies]
extensions = []
```

---

## 4. Extension 与 Core 的交互契约

### Extension 能做的事情（通过 Core 提供的挂载点）

1. **注册新的 Hook trigger + handler** — Extension 的 Hook 在 zchat-acp 进程内执行（runtime="zchat"），handler 指向 Extension 包内的 Python callable
2. **注册新的 ContentType** — 声明新的 content_type。Core 的宽容路由已经能传输未知类型，注册后 Extension 的 Hook 可以处理这些 event
3. **注册新的 Index pattern** — Zenoh key-expression。Core 的 com daemon 会为新 pattern 创建 subscriber/queryable
4. **注册新的 Annotation key** — Core 路由层透传未知 annotation
5. **注册新的 ZChat Operation type** — Core 对未知 type 的 ZChatEvent 做透传
6. **注册新的 CLI 子命令** — 通过 Python entry_point 注册到 zchat-cli

### Extension 不能做的事情

- 修改 Core 的路由逻辑（event_router 封闭）
- 绕过 Access 检查
- 修改已有 Operation type 的语义
- 直接操作 Zenoh session（必须通过 com 层 API）

---

## 5. 宽容路由与未处理提示

Core 收到 content_type 不在已注册 ContentType 中的 event 时：

```python
async def route_event(self, event: ZChatEvent):
    # 1. 结构校验
    validate_structure(event)  # 必须有 id/room/type/from/timestamp/content
    
    # 2. 宽容存储
    self.event_store.put(event)
    
    # 3. 路由
    await self.publish(event)
    
    # 4. Hook pipeline
    handlers = self.extension_registry.get_hooks(event.type)
    if handlers:
        for handler in handlers:
            await handler(event)
    else:
        # 5. 无 handler → 检查是否是 extension event
        if self._looks_like_extension_event(event):
            ext_name = self._infer_extension_name(event.content_type)
            await self.emit_local_hint(
                f"收到 {event.content_type} 类型的消息，"
                f"需要安装 ext-{ext_name} 才能处理。\n"
                f"运行: zchat ext install {ext_name}"
            )
```

**content_type 命名约定（MIME 格式）**：

```
Core types (short → MIME):
  text/plain                    → text/plain
  acp.*                         → application/vnd.zchat.acp.*
  system-event                  → application/vnd.zchat.system-event
  spawn-config                  → application/vnd.zchat.spawn-config

Extension types (short → MIME):
  ext.{name}.{subtype}          → application/vnd.zchat-ext.{name}.{subtype}

例:
  ext.migrate.migration-bundle  → application/vnd.zchat-ext.migrate.migration-bundle
  ext.offline.relay-request     → application/vnd.zchat-ext.offline.relay-request
  ext.socialware.shadow-message → application/vnd.zchat-ext.socialware.shadow-message
```

从 MIME `application/vnd.zchat-ext.migrate.migration-bundle` 提取 `migrate` → 提示安装 `ext-migrate`。

---

## 6. 热加载

### 安装流程

```
zchat ext install migrate
  │
  ├── 1. pip install zchat-ext-migrate (subprocess)
  │
  ├── 2. 扫描新包的 extension.toml
  │
  ├── 3. 增量注册（不重启 daemon）:
  │     ├── ContentType registry += ext.migrate.migration-bundle, ...
  │     ├── Hook registry += on_migrate_out, on_migrate_in
  │     ├── Index registry += 新 pattern → Zenoh 新增 subscriber/queryable
  │     ├── CLI registry += session grant, session reclaim
  │     └── 标记 extension 状态为 active
  │
  ├── 4. 回扫 Event Store（关键步骤）:
  │     扫描近期未处理的 event（content_type 匹配新注册的 ContentType）
  │     → 对这些 event 重新触发 Hook pipeline
  │     → mark_handled 保证幂等性
  │
  └── 5. 广播 SystemEvent: "bob 已安装 ext-migrate"
```

### 卸载流程

```
zchat ext uninstall migrate
  │
  ├── 1. 从各 registry 注销
  │
  ├── 2. Zenoh 取消相关 subscriber/queryable
  │
  ├── 3. pip uninstall zchat-ext-migrate
  │
  └── 4. Event Store 中的相关 event 不删除（宽容存储）
```

### 热加载实现

Extension Registry 是 zchat 进程级的全局单例，com 和 acp 子模块共享。

```python
class ExtensionRegistry:
    """线程安全的 Extension 注册表"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._extensions: dict[str, LoadedExtension] = {}
        self._hook_registry: dict[str, list[HookHandler]] = {}
        self._datatype_registry: dict[str, ContentTypeDef] = {}
    
    def load(self, manifest_path: str) -> None:
        """热加载一个 extension"""
        manifest = parse_manifest(manifest_path)
        
        # 动态 import extension 的 Python module
        for hook_def in manifest.hooks:
            module_name, func_name = hook_def.handler.split(":")
            module = importlib.import_module(f"zchat_ext_{manifest.name}.{module_name}")
            handler = getattr(module, func_name)
            hook_def.resolved_handler = handler
        
        with self._lock:
            self._extensions[manifest.name] = LoadedExtension(manifest, ...)
            for hook_def in manifest.hooks:
                self._hook_registry.setdefault(hook_def.trigger, []).append(hook_def)
                self._hook_registry[hook_def.trigger].sort(key=lambda h: h.priority)
            for dt in manifest.content_types:
                self._datatype_registry[dt.标识符] = dt
    
    def unload(self, name: str) -> None:
        """热卸载一个 extension"""
        with self._lock:
            ext = self._extensions.pop(name, None)
            if ext:
                # 从各 sub-registry 移除
                ...
```

用 `RLock` 保证线程安全。Extension 加载/卸载是低频操作，锁争用不会成为瓶颈。

---

## 7. 回扫机制（Replay）

热加载后回扫是让流程闭环的关键——bob 安装了 ext-migrate 后可以处理之前收到的 migration-bundle。

```python
async def replay_unhandled_events(
    ext: LoadedExtension,
    event_store: EventStore,
    hook_dispatcher: HookDispatcher,
):
    """回扫 Event Store 中与新加载 extension 相关的未处理 event"""
    
    recent_events = event_store.query(
        since=datetime.now() - timedelta(hours=1),  # 默认 1 小时，可配置
        content_types=ext.registered_data标识符s,
    )
    
    for event in recent_events:
        if not event_store.is_handled(event.id, ext.name):
            await hook_dispatcher.dispatch(event, source="replay")
            event_store.mark_handled(event.id, ext.name)
```

**回扫边界**：
- 时间窗口：默认 1 小时（可配置）
- 幂等性：`mark_handled` 保证不重复处理
- source 标记：Hook handler 可通过 `source="replay"` 区分首次和回扫

---

## 8. Extension 目录结构

```
zchat-ext-migrate/
├── extension.toml           ← manifest
├── schemas/
│   ├── migration-bundle.json
│   └── session-end-bundle.json
├── zchat_ext_migrate/
│   ├── __init__.py
│   ├── hooks.py             ← bundle_pack, bundle_restore
│   ├── cli.py               ← grant_cmd, reclaim_cmd
│   └── access.py            ← grant/reclaim 权限逻辑
└── tests/
    └── ...
```

Python 包命名规范：`zchat-ext-{name}`（pip 包名），`zchat_ext_{name}`（Python module 名）。

---

## 9. Extension 间的依赖

v0.0.6.3 使用扁平依赖列表，不做版本范围解析。

```toml
[dependencies]
extensions = []  # 简单列表，不允许循环依赖
```

Extension 内部的模块分层（如 Socialware 内部 EventWeaver/AgentForge/Respool/TaskArena）由 Extension 自己管理，不暴露给 Core。

---

## 10. 典型交互流程

```
场景：alice (有 ext-migrate) 执行 grant，bob 没有 ext-migrate

1. alice: zchat session grant ppt-maker bob
   → ext-migrate 的 grant_cmd 执行
   → 打包 MigrationBundle
   → ZChatEvent(content_type="application/vnd.zchat-ext.migrate.migration-bundle") → Zenoh publish

2. bob 的 core 收到 event
   → 宽容路由：存储 + 透传
   → 无 handler → 从 MIME 推断 ext name: zchat-ext.migrate → "migrate"
   → bob 看到: "收到 ext.migrate.migration-bundle 类型消息，运行 zchat ext install migrate"

3. bob: zchat ext install migrate
   → pip install zchat-ext-migrate
   → 热加载 → registry 更新
   → 回扫：找到之前的 migration-bundle event
   → ext-migrate 的 bundle_restore hook 处理
   → 迁移完成
```

---

## 相关文档

- [架构概览](./01-overview.md) · [zchat-protocol](./03-protocol.md)
- [zchat-com](./04-com.md) · [zchat-acp](./05-acp.md) · [zchat-cli](./02-cli.md)
- [E2E](./08-e2e-scenarios.md) · [测试](./11-mvp-testcases.md)
