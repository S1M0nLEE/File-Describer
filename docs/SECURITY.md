# 安全说明

FileKG 设计为**本地个人工具**。默认绑定 `127.0.0.1`，不对公网暴露。

## 默认安全 posture

| 项 | 默认 |
|----|------|
| 监听地址 | `127.0.0.1:8765`（`config.yaml` → `api.host`） |
| API 鉴权 | 关闭；可通过 Token 启用 |
| 索引路径 | 仅 `$HOME`、项目 `data/`、仓库根目录 |
| 文件列表路径 | 脱敏为 `~/…`（`api.expose_full_paths: false`） |
| 500 错误 | 不返回内部异常字符串 |

## 启用 API Token

1. 生成随机 token，写入 `.env`：
   ```bash
   FILEKG_API_TOKEN=your-random-token
   ```
2. 在 `config.yaml` 设置：
   ```yaml
   api:
     token: ""          # 也可直接写此处，优先读环境变量
     require_token: true
   ```
3. 客户端请求携带：
   ```http
   Authorization: Bearer your-random-token
   ```

公开路径（无需 Token）：`/`, `/health`, `/health/diagnostics`, `/static/*`, `/docs`, `/openapi.json`

## 索引路径 allowlist

`POST /index`、`POST /watch` 会校验目标路径。默认允许：

- 用户主目录 `$HOME` 下任意子目录
- 项目 `data/` 目录
- 仓库根目录

限制到特定目录：

```yaml
api:
  index_allow_roots:
    - "${HOME}/Documents"
    - "./data"
```

## Docker / 局域网访问

容器内需对外暴露端口时，在 `docker-compose.yml` 设置：

```yaml
environment:
  FILEKG_HOST: "0.0.0.0"
```

**同时务必启用 API Token**，切勿在无 Token 情况下将服务映射到公网。

## 敏感操作

以下端点会修改索引或读取本机文件，部署到非本机环境前请评估：

- `POST /index` — 索引目录
- `POST /rag/index-local` — 批量索引用户目录
- `POST /watch` — 文件监控
- `POST /admin/heartbeat` — 增量索引
- `POST /workflow/import-etw` — 读取 CSV

## 报告问题

请勿在 Issue 中粘贴含真实路径、API Key 的日志。见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
