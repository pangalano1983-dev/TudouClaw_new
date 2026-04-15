# DevOps 部署模版 (DevOps & Deployment Template)

**tags:** devops, ci-cd, deployment, infrastructure, monitoring
**roles:** DevOps Engineer, Release Manager, Infrastructure Engineer
**category:** Operations

## 目标 (Objective)

设计和实施可靠的 CI/CD 管道、容器化和部署流程，实现自动化、快速和安全的发布。

## CI/CD 管道设计 (CI/CD Pipeline Design)

### 管道阶段 (Pipeline Stages)

```
┌─────────────┐
│   Trigger   │  - 代码提交/PR
└──────┬──────┘
       ↓
┌─────────────┐
│    Build    │  - 编译、依赖、打包
└──────┬──────┘
       ↓
┌─────────────┐
│    Test     │  - 单元测试、集成测试
└──────┬──────┘
       ↓
┌─────────────┐
│    Scan     │  - 安全扫描、代码质量
└──────┬──────┘
       ↓
┌─────────────┐
│   Stage     │  - 暂存环境部署
└──────┬──────┘
       ↓
┌─────────────┐
│     QA      │  - 测试验证
└──────┬──────┘
       ↓
┌─────────────┐
│  Approve    │  - 手动审批
└──────┬──────┘
       ↓
┌─────────────┐
│   Prod      │  - 生产部署
└──────┬──────┘
       ↓
┌─────────────┐
│  Monitor    │  - 监控和验证
└─────────────┘
```

### 触发规则 (Trigger Rules)

- [ ] 代码提交自动触发
- [ ] PR 创建后运行
- [ ] 定时计划（每日构建）
- [ ] 手动触发（生产版本）
- [ ] Webhook 触发（外部事件）

### 构建配置 (Build Configuration)

```
项目: [项目名称]
构建工具: [Maven/Gradle/npm/pip]
JDK/Runtime: [版本]

步骤:
1. [ ] 清理
   command: clean

2. [ ] 依赖下载
   command: install/npm install

3. [ ] 编译
   command: compile

4. [ ] 单元测试
   command: test
   coverage: >= 80%

5. [ ] 打包
   command: package
   artifact: [file.jar/file.zip]

6. [ ] 上传制品库
   repository: [Nexus/Artifactory]
   version: [自动版本]
```

### 测试阶段 (Test Stage)

```
单元测试:
- [ ] 执行所有单元测试
- [ ] 覆盖率报告 >= 80%
- [ ] 失败则中断管道

集成测试:
- [ ] 启动测试环境
- [ ] 运行集成测试套件
- [ ] 清理测试数据

性能测试:
- [ ] JMeter 基准测试
- [ ] 响应时间 < [X]ms
- [ ] 吞吐量 > [X] req/sec

E2E 测试:
- [ ] Selenium/Cypress 测试
- [ ] 用户流程验证
- [ ] 浏览器兼容性
```

### 扫描阶段 (Scan Stage)

```
安全扫描:
- [ ] SAST (静态分析)
  tool: [SonarQube/Checkmarx]
  quality_gate: pass

- [ ] 依赖漏洞
  tool: [Snyk/OWASP Dep-Check]
  CVE_critical: 0

- [ ] 容器镜像扫描
  tool: [Trivy/Harbor]
  high_severity: 0

代码质量:
- [ ] SonarQube 分析
  complexity: < 15
  duplication: < 3%
  coverage: >= 80%

- [ ] Lint 检查
  tool: [ESLint/Pylint]
  errors: 0
  warnings: < 5
```

## 容器化检查清单 (Containerization Checklist)

### Docker 镜像构建 (Docker Image Build)

```dockerfile
# Dockerfile 最佳实践

# [ ] 使用官方基础镜像
FROM ubuntu:22.04

# [ ] 安装依赖最小化
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# [ ] 多阶段构建（减小镜像大小）
FROM ubuntu:22.04 as builder
WORKDIR /build
COPY . .
RUN make build

FROM ubuntu:22.04
COPY --from=builder /build/output /app

# [ ] 设置合适的工作目录
WORKDIR /app

# [ ] 不使用 root 用户
RUN useradd -m appuser
USER appuser

# [ ] 暴露必要的端口
EXPOSE 8080

# [ ] 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8080/health || exit 1

# [ ] 启动命令
CMD ["java", "-jar", "app.jar"]
```

### 镜像优化 (Image Optimization)

- [ ] 镜像大小: < 500MB（或指定目标）
- [ ] 层数最小化
- [ ] 只包含必要文件
- [ ] 多阶段构建使用
- [ ] 层缓存充分利用

### 镜像安全扫描 (Image Security Scanning)

```
扫描工具: [Trivy/Clair]
扫描命令: docker scan [image]

检查项:
- [ ] 已知漏洞 (CVE)
  critical: 0
  high: 0

- [ ] 恶意软件扫描

- [ ] 配置错误检查
  - 以 root 运行
  - 特权标志
  - 不安全的权限
```

### 镜像仓库 (Image Registry)

```
仓库类型: [Docker Hub/ECR/Harbor]
仓库 URL: [registry.example.com]

安全配置:
- [ ] 镜像签名启用
- [ ] 访问控制配置
- [ ] 镜像扫描启用
- [ ] 漏洞报告

镜像版本:
- [ ] 标签策略: [latest/semantic]
- [ ] 保留策略: 保留最后 [N] 个版本
- [ ] 清理策略: 过期 [X] 天后清理
```

## 监控设置 (Monitoring Setup)

### 应用监控 (Application Monitoring)

```
指标收集:
- [ ] Prometheus
  scrape_interval: 15s
  retention: 15d

关键指标:
- [ ] HTTP 请求率
  metric: http_requests_total
  labels: method, status, path

- [ ] 响应时间
  metric: http_request_duration_seconds
  buckets: [0.1, 0.5, 1, 2, 5]

- [ ] 错误率
  metric: http_requests_failed_total
  alert: > 5%

- [ ] JVM 指标
  metric: jvm_memory_used_bytes
  metric: jvm_threads_live

- [ ] 数据库指标
  metric: db_connection_pool_active
  metric: db_query_duration
  alert: > 1s
```

### 日志聚合 (Log Aggregation)

```
日志系统: [ELK Stack/Splunk]

日志收集:
- [ ] 应用日志
  path: /var/log/app.log
  format: JSON

- [ ] 系统日志
  source: syslog

- [ ] 访问日志
  source: nginx/apache

日志级别:
- [ ] ERROR: 所有错误记录
- [ ] WARN: 警告信息
- [ ] INFO: 关键业务事件
- [ ] DEBUG: 不在生产中记录

保留策略:
- [ ] ERROR: 90 天
- [ ] WARN: 30 天
- [ ] INFO: 7 天
- [ ] DEBUG: 不保留
```

### 告警规则 (Alerting Rules)

| 告警名称 | 条件 | 阈值 | 严重程度 | 处理人 |
|---------|------|------|--------|-------|
| 高错误率 | 错误率 > 5% | 5 分钟 | P1 | [团队] |
| 高延迟 | p95 延迟 > 1s | 10 分钟 | P2 | [团队] |
| 磁盘空间 | 磁盘使用 > 85% | 即时 | P2 | [DevOps] |
| 内存泄漏 | 内存占用持续增长 | 15 分钟 | P1 | [开发] |
| 数据库连接 | 活跃连接 > 80% | 5 分钟 | P1 | [DBA] |

## 事件响应手册 (Incident Response Playbook)

### 事件分类 (Incident Classification)

```
P0 (关键): 服务完全不可用
- [ ] 立即切换到备用系统
- [ ] CEO 通知
- [ ] 公开通信启动

P1 (严重): 部分功能受影响
- [ ] 快速根因分析
- [ ] 临时缓解
- [ ] 内部通信

P2 (中等): 有限影响或性能下降
- [ ] 协作团队诊断
- [ ] 优化缓解措施

P3 (低): 次要问题或不便
- [ ] 记录问题
- [ ] 计划修复
```

### 响应流程 (Response Process)

```
1. 检测 (Detection)
   - [ ] 监控告警触发
   - [ ] 用户报告
   - [ ] 时间: 0 分钟

2. 确认 (Confirmation)
   - [ ] 验证事件真实性
   - [ ] 确定严重程度
   - [ ] 时间: < 5 分钟

3. 沟通 (Communication)
   - [ ] Slack 通知关键团队
   - [ ] 启动事故管理
   - [ ] 时间: < 10 分钟

4. 缓解 (Mitigation)
   - [ ] 实施临时修复
   - [ ] 恢复服务
   - [ ] 时间: < 30 分钟 (P1)

5. 根本原因分析 (Root Cause)
   - [ ] 深入调查
   - [ ] 文档化原因
   - [ ] 时间: < 24 小时

6. 修复 (Remediation)
   - [ ] 实施永久修复
   - [ ] 代码审查和测试
   - [ ] 部署修复
   - [ ] 时间: < 1 周

7. 回顾 (Post-Mortem)
   - [ ] 事后总结会议
   - [ ] 文档化学习
   - [ ] 改进行动项
   - [ ] 时间: < 2 周
```

### 常见故障排查 (Common Troubleshooting)

```
故障: 服务无响应

诊断步骤:
1. [ ] 检查网络连接
   cmd: ping host
   cmd: telnet host 8080

2. [ ] 检查进程状态
   cmd: ps aux | grep java

3. [ ] 检查日志
   cmd: tail -f /var/log/app.log

4. [ ] 检查端口
   cmd: netstat -tlnp | grep 8080

5. [ ] 检查资源
   cmd: top, free -h

快速修复:
- [ ] 重启服务: systemctl restart app
- [ ] 清理缓存: redis-cli FLUSHALL
- [ ] 数据库连接重置
- [ ] 故障转移到备用
```

## 回滚策略 (Rollback Strategy)

### 蓝绿部署 (Blue-Green Deployment)

```
部署模式:
1. [ ] 蓝环境（当前生产）- 保持运行
2. [ ] 绿环境（新版本）- 完全部署和测试
3. [ ] 流量切换 - 从蓝到绿
4. [ ] 监控 - 绿环境验证
5. [ ] 回滚 - 切换回蓝（如需要）

优点:
- 快速回滚 (< 1 分钟)
- 零停机时间
- 完整测试

缺点:
- 2 倍基础设施成本
- 数据库迁移复杂
```

### 金丝雀部署 (Canary Deployment)

```
部署阶段:
1. [ ] 部署到 1% 服务器
   流量: 1%
   监控: 错误率、延迟
   时间: 15 分钟

2. [ ] 部署到 10% 服务器
   流量: 10%
   监控: 所有指标
   时间: 30 分钟

3. [ ] 部署到 50% 服务器
   流量: 50%
   关键指标验证
   时间: 1 小时

4. [ ] 部署到 100% 服务器
   流量: 100%
   持续监控

回滚标准:
- [ ] 错误率 > 1%
- [ ] p95 延迟 > 2x 基线
- [ ] CPU > 90%
```

### 滚动更新 (Rolling Update)

```
配置:
maxSurge: 25%      # 超过期望副本的百分比
maxUnavailable: 25% # 不可用副本的百分比
minReadySeconds: 30 # 就绪前等待时间

流程:
1. 启动新 pod
2. 等待就绪
3. 移除旧 pod
4. 重复直到完成

时间: [部署时间]
监控: 每个 pod
```

### 回滚触发 (Rollback Trigger)

- [ ] 自动: 健康检查失败
- [ ] 自动: 错误率阈值超过
- [ ] 手动: 运维人员决定
- [ ] 手动: 管理员命令

回滚命令:
```bash
# Kubernetes
kubectl rollout undo deployment/myapp

# Docker Swarm
docker service update --image old:version myapp

# Terraform
terraform destroy -target=aws_instance.new
```

## 部署检查清单 (Deployment Checklist)

### 部署前 (Pre-Deployment)

- [ ] 所有测试通过
- [ ] 代码审查批准
- [ ] 安全扫描清除
- [ ] 依赖更新完成
- [ ] 数据库迁移脚本验证
- [ ] 配置变更审查
- [ ] 备份完成
- [ ] 团队通知
- [ ] 维护窗口预留
- [ ] 客户/用户通知

### 部署中 (During Deployment)

- [ ] 监控仪表板打开
- [ ] 日志流监控
- [ ] 性能基线记录
- [ ] 关键路径测试
- [ ] 依赖服务检查
- [ ] 团队在线沟通

### 部署后 (Post-Deployment)

- [ ] 功能验证测试
- [ ] 冒烟测试通过
- [ ] 性能指标正常
- [ ] 错误率正常
- [ ] 用户反馈收集
- [ ] 文档更新
- [ ] 团队总结

## 灾难恢复计划 (Disaster Recovery Plan)

| 场景 | RTO | RPO | 恢复步骤 |
|------|-----|-----|---------|
| 数据库故障 | 15 分钟 | 5 分钟 | 从备份恢复，验证数据 |
| 网络中断 | 10 分钟 | 0 分钟 | 故障转移到备用网络 |
| 区域故障 | 1 小时 | 15 分钟 | 故障转移到备用区域 |
| 数据损坏 | 2 小时 | 1 小时 | 从备份恢复，检查数据 |

**测试频率**: [ ] 每月 / [ ] 每季度 / [ ] 每半年
**最后测试**: [日期]
**下次计划测试**: [日期]
