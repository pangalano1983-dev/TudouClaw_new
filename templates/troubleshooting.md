# 故障排查模版 (Troubleshooting Template)

**tags:** troubleshooting, debugging, root-cause-analysis, incident-management
**roles:** DevOps Engineer, SRE, Support Engineer, Technical Lead
**category:** Operations

## 目标 (Objective)

系统化地诊断和解决问题，快速恢复服务并防止再次发生。

## 根本原因分析 (Root Cause Analysis)

### 5Why 分析法 (5 Whys Method)

```
问题: 生产服务在晚上 8 点宕机

Why 1: 为什么服务宕机?
答: 内存溢出异常导致进程崩溃

Why 2: 为什么内存溢出?
答: 缓存没有正确清理，导致内存持续增长

Why 3: 为什么缓存没有清理?
答: 缓存淘汰策略在最近一次代码更新中被删除

Why 4: 为什么被删除?
答: 代码审查时没有注意到这个改变

Why 5: 为什么代码审查没有检查到?
答: 没有关于缓存管理的检查清单

根本原因: 缺少缓存清理策略和代码审查检查清单

解决方案:
[ ] 恢复缓存淘汰策略
[ ] 添加内存监控告警
[ ] 创建代码审查检查清单
[ ] 培训开发人员缓存最佳实践
```

### 因果分析 (Fishbone Diagram)

```
                        人员                  流程                   技术
                         │                     │                      │
                    缺少培训              代码审查不严格    缺少监控告警
                         │                     │                      │
                         ├─────────────────────┼──────────────────────┤
                                               │                      │
                                       缓存溢出事件
                                               │
                         ┌─────────────────────┼──────────────────────┐
                         │                     │                      │
                      环境                   数据                    基础设施
                      │                      │                       │
              升级配置变更          数据量增加      内存大小不足
```

### 时间线分析 (Incident Timeline)

```
时间        事件                                   判断/行动
─────────────────────────────────────────────────────────────────
20:00:00   监控告警：错误率 > 5%                    立即通知团队
20:00:30   用户反馈：服务不可用                     确认 P0 事件
20:01:00   查看日志：内存溢出异常                   开始根因分析
20:02:00   临时缓解：重启服务                       服务恢复（缓解）
20:03:00   团队到位                                 深入调查开始
20:15:00   发现：缓存没有清理                       确定根本原因
20:20:00   修复：恢复缓存淘汰代码                   推送到 staging
20:30:00   验证修复                                 部署到生产
20:45:00   监控验证                                 确认问题解决
21:00:00   事件关闭                                 进行事后总结

关键指标:
- 发现时间: 1 分钟 (MTTD)
- 响应时间: 3 分钟 (MTTR)
- 恢复时间: 45 分钟（临时），修复后持久恢复
- 影响用户: ~5000 个
- 影响时间: 5 分钟（完全不可用）+ 20 分钟（降级）
```

## 故障诊断 (Troubleshooting Diagnosis)

### 分层诊断流程 (Layered Diagnosis)

```
1. 应用层 (Application Layer)
   ├── [ ] 应用进程运行状态
   │   cmd: ps aux | grep java
   │   cmd: systemctl status myapp
   │
   ├── [ ] 应用日志
   │   cmd: tail -f /var/log/app.log
   │   查看: ERROR, EXCEPTION, CRITICAL
   │
   ├── [ ] 应用指标
   │   监控: CPU, 内存, GC
   │   工具: JProfiler, YourKit
   │
   └── [ ] 应用依赖
       cmd: lsof -p [PID] | grep socket

2. 系统层 (System Layer)
   ├── [ ] CPU 使用率
   │   cmd: top, htop
   │   正常: < 80%
   │
   ├── [ ] 内存使用
   │   cmd: free -h
   │   正常: 可用内存 > 10%
   │
   ├── [ ] 磁盘空间
   │   cmd: df -h
   │   正常: 使用 < 85%
   │
   ├── [ ] 进程数
   │   cmd: ps aux | wc -l
   │   正常: < 系统限制
   │
   └── [ ] 文件描述符
       cmd: lsof | wc -l
       正常: < ulimit -n

3. 网络层 (Network Layer)
   ├── [ ] 网络连接
   │   cmd: netstat -tlnp | grep LISTEN
   │   检查: 端口是否监听
   │
   ├── [ ] DNS 解析
   │   cmd: nslookup example.com
   │   cmd: dig example.com
   │
   ├── [ ] 网络延迟
   │   cmd: ping example.com
   │   正常: < 100ms
   │
   └── [ ] 防火墙规则
       cmd: iptables -L -n
       检查: 端口是否开放

4. 数据库层 (Database Layer)
   ├── [ ] 连接状态
   │   cmd: psql -U user -h host -d db -c "SELECT 1"
   │
   ├── [ ] 连接池
   │   监控: 活跃连接、等待队列
   │   告警: > 80% 使用率
   │
   ├── [ ] 查询性能
   │   工具: EXPLAIN ANALYZE
   │   查看: 慢查询日志
   │
   └── [ ] 数据容量
       cmd: SELECT pg_size_pretty(pg_database_size('db_name'));

5. 外部依赖 (External Dependencies)
   ├── [ ] 第三方 API
   │   检查: 状态页面
   │   测试: curl 调用
   │
   └── [ ] 缓存层
       cmd: redis-cli ping
       cmd: redis-cli INFO stats
```

## 常见问题诊断 (Common Issues Diagnosis)

### 高 CPU 使用率 (High CPU Usage)

```
症状: CPU > 80%

诊断步骤:
1. [ ] 识别高 CPU 进程
   cmd: top -b -n 1 | head -n 20

   找出: PID 和 %CPU

2. [ ] 分析该进程
   cmd: ps aux | grep [PID]

   检查: 命令行、运行时间

3. [ ] 查看进程堆栈
   cmd: jstack [PID] > dump.txt

   分析: 热点线程、死循环

4. [ ] 查看进程内存
   cmd: jmap -heap [PID]

   检查: 堆大小、GC 统计

可能原因和解决:
- 无限循环: [ ] 修复代码
- 高频操作: [ ] 优化算法、添加缓存
- GC 频繁: [ ] 增加堆大小、优化对象创建
- 外部 API 慢: [ ] 超时配置、降级方案

临时缓解:
[ ] 重启进程
[ ] 扩展资源（CPU 核心）
```

### 高内存使用率 (High Memory Usage)

```
症状: 内存 > 90%, OOM 异常, GC pause 长

诊断步骤:
1. [ ] 检查内存使用
   cmd: free -h
   cmd: top -b -n 1 | grep VIRT

2. [ ] 分析堆栈转储
   cmd: jmap -dump:live,format=b,file=heap.bin [PID]

   分析工具: JProfiler, MAT (Memory Analyzer Tool)

3. [ ] 查看 GC 日志
   cmd: jstat -gc [PID] 1000

   监控: Full GC 频率、暂停时间

可能原因:
- [ ] 内存泄漏: 对象没有被释放
- [ ] 缓存未设置 TTL: 缓存无限增长
- [ ] 频繁创建大对象: 字符串连接、序列化
- [ ] 依赖项泄漏: 第三方库问题

解决方案:
1. 代码修复:
   [ ] 移除循环引用
   [ ] 设置缓存 TTL
   [ ] 使用对象池
   [ ] 及时关闭资源

2. JVM 调整:
   -Xms: 初始堆大小
   -Xmx: 最大堆大小
   -XX:+HeapDumpOnOutOfMemoryError: 内存不足时生成转储

3. 监控和告警:
   [ ] 内存使用 > 80% 告警
   [ ] Full GC 频率 > X/分钟 告警
```

### 数据库连接耗尽 (Database Connection Pool Exhausted)

```
症状:
- "No more connections available"
- 应用超时
- 数据库连接数 == 最大值

诊断步骤:
1. [ ] 查看连接池状态
   SQL: SELECT count(*) FROM pg_stat_activity;

   检查: 活跃连接、空闲连接

2. [ ] 识别持有连接的应用
   SQL: SELECT application_name, count(*)
        FROM pg_stat_activity
        GROUP BY application_name;

3. [ ] 查看慢查询
   SQL: SELECT * FROM pg_stat_statements
        ORDER BY mean_time DESC LIMIT 10;

   查看: 平均时间、总耗时

4. [ ] 检查锁
   SQL: SELECT * FROM pg_locks
        WHERE NOT granted;

可能原因:
- [ ] 查询慢: 一个查询占用连接很久
- [ ] 连接泄漏: 应用没有释放连接
- [ ] 峰值流量: 并发连接数增加
- [ ] 死锁: 事务互相等待

解决方案:
1. 立即缓解:
   [ ] 杀死慢查询: SELECT pg_terminate_backend(pid);
   [ ] 重启应用连接池

2. 根本修复:
   [ ] 优化慢查询（添加索引）
   [ ] 增加连接池大小（临时）
   [ ] 改进连接管理（关闭未使用的）
   [ ] 实现连接重用和超时

3. 监控:
   [ ] 活跃连接 > 80% 告警
   [ ] 等待连接队列 > 0 告警
```

## 意外行为诊断 (Unexpected Behavior Diagnosis)

### API 返回错误响应 (API Returning Errors)

```
错误: 某个端点始终返回 500

诊断:
1. [ ] 检查日志
   cmd: tail -f /var/log/app.log | grep -A 5 ERROR

   查看: 异常类型、堆栈跟踪

2. [ ] 复现问题
   cmd: curl -v https://api.example.com/endpoint

   记录: 请求头、响应头、响应体

3. [ ] 检查依赖
   - 数据库是否可连接
   - 缓存是否可连接
   - 外部 API 是否可用

4. [ ] 检查权限
   - 数据库用户权限
   - 文件系统权限
   - IAM 权限

5. [ ] 追踪请求
   - 请求 ID 追踪
   - 分布式跟踪系统
   - 日志聚合

常见原因:
[ ] NullPointerException: 对象为 null
[ ] 数据库错误: 连接、查询、约束
[ ] 外部 API 超时: 第三方服务不可用
[ ] 权限错误: 没有足够的权限
[ ] 资源耗尽: 内存、连接池等
```

### 数据不一致 (Data Inconsistency)

```
问题: 数据库中的数据与应用的期望不符

诊断:
1. [ ] 验证数据库数据
   SQL: SELECT * FROM users WHERE id = '123';

   对比: 应用日志中的预期值

2. [ ] 检查最近的变更
   SQL: SELECT * FROM audit_log WHERE entity_id = '123' ORDER BY created_at DESC;

   分析: 谁改的、何时改的、改了什么

3. [ ] 检查是否有并发修改
   分析: 是否有竞态条件

   案例: 用户 A 和 B 同时更新同一条记录

可能原因:
[ ] 缺少事务隔离: 未使用事务
[ ] 竞态条件: 并发修改
[ ] 乐观锁失败: 版本号不匹配
[ ] 应用程序 bug: 逻辑错误
[ ] 缓存陈旧: 缓存没有失效

解决方案:
[ ] 添加悲观锁或乐观锁
[ ] 使用事务确保一致性
[ ] 改进缓存失效策略
[ ] 添加审计日志
```

## 性能问题诊断 (Performance Issue Diagnosis)

### 响应时间慢 (Slow Response Time)

```
问题: API 端点响应时间从 100ms 增加到 1000ms

诊断:
1. [ ] 缩小范围: 是所有端点还是特定端点

2. [ ] 检查数据库性能
   SQL: EXPLAIN ANALYZE SELECT ...;

   查看: 执行计划、扫描行数

3. [ ] 检查应用日志
   查看: 业务逻辑执行时间、外部调用时间

4. [ ] 分布式追踪
   工具: Jaeger, Zipkin
   查看: 各个服务的耗时

5. [ ] 系统资源
   [ ] CPU: top
   [ ] 内存: free
   [ ] I/O: iostat
   [ ] 网络: iftop

可能原因和快速检查:
┌──────────────────┬──────────────────┬──────────────────┐
│ 原因             │ 快速检查          │ 解决方案          │
├──────────────────┼──────────────────┼──────────────────┤
│ 缓存失效         │ 缓存命中率下降    │ 预热缓存          │
│ 并发增加         │ 连接池等待        │ 扩展资源          │
│ 代码变更         │ 对比最近提交      │ 回滚或优化        │
│ 数据量增加       │ 表大小增加        │ 添加索引、分区    │
│ 慢查询           │ EXPLAIN 分析      │ 优化查询          │
│ GC 暂停          │ GC 日志           │ 调整堆、优化对象  │
└──────────────────┴──────────────────┴──────────────────┘
```

## 恢复清单 (Recovery Checklist)

### 立即行动 (Immediate Actions)

```
发现问题后的前 5 分钟:

[ ] 确认问题存在和严重程度
[ ] 启动事件响应流程
[ ] 通知相关团队（Slack / 页面提醒）
[ ] 开始记录事件时间线
[ ] 保留现场证据（日志转储、内存转储）
[ ] 准备临时缓解措施

如果服务完全宕机:
[ ] 尝试立即重启
[ ] 如果重启失败，故障转移到备用
[ ] 启用降级或维护页面
```

### 调查阶段 (Investigation Phase)

```
前 15 分钟:

[ ] 运行诊断命令收集信息
[ ] 检查监控仪表板
[ ] 查看最近的变更/部署
[ ] 查看日志和指标
[ ] 初步识别可能原因
```

### 修复阶段 (Remediation Phase)

```
[ ] 实施修复（如果知道原因）
[ ] 部署修复到 staging 验证
[ ] 部署修复到生产
[ ] 验证问题解决
[ ] 监控修复后的表现

修复失败的回滚计划:
[ ] 回滚到上一个稳定版本
[ ] 时间: < 5 分钟
```

### 验证和关闭 (Verification & Closure)

```
修复后:

[ ] 验证所有功能正常
[ ] 检查相关系统是否受影响
[ ] 验证性能恢复
[ ] 确认不再有告警
[ ] 关闭事件
```

## 预防措施 (Prevention Measures)

### 监控覆盖 (Monitoring Coverage)

```
必须监控的指标:
[ ] 应用
  - 错误率: 告警 > 1%
  - 响应时间: 告警 p95 > 2x 基线
  - 吞吐量: 告警 < 平均的 50%

[ ] 系统
  - CPU: 告警 > 80%
  - 内存: 告警 > 85%
  - 磁盘: 告警 > 80%
  - 进程: 告警数量异常

[ ] 数据库
  - 连接数: 告警 > 80% 容量
  - 慢查询: 告警 > 100ms
  - 锁冲突: 告警任何锁

[ ] 外部依赖
  - 可用性: 告警 downtime
  - 延迟: 告警 > 基线
```

### 预警指标 (Precursor Metrics)

```
问题发生前的信号:

内存泄漏预警:
- [ ] 堆内存持续增长（周期内）
- [ ] Full GC 频率增加
- [ ] 年轻代 GC 也变长

性能下降预警:
- [ ] P95 延迟开始上升
- [ ] 缓存命中率下降
- [ ] 数据库连接数增加

容量问题预警:
- [ ] 磁盘空间持续减少
- [ ] 数据库大小每天增长 X GB
- [ ] 连接数接近限制

行动:
[ ] 设置预警告警（比故障告警早）
[ ] 自动扩展资源
[ ] 自动清理
```
