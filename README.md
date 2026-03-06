# Gallery CMS / 视觉创作集管理系统

一个基于 **Flask** 的个人作品集与内容管理系统，支持图片 / 视频 / 3D 模型展示，含前台页面与后台管理。

---

## 0. 5分钟快速上线（必看）

### A. Windows 本地快速启动

```powershell
# 1) 进入项目目录
cd c:\Users\Administrator\Desktop\gallery_site

# 2) 安装依赖
pip install -r requirements.txt

# 3) 启动
python app.py
```

如果提示5000端口占用

1、查找占用端口程序
netstat -ano | findstr :5000
2、结束占用端口程序
taskkill /F /PID 123456

访问：

- 前台：`http://localhost:5000`
- 后台：`http://localhost:5000/admin/login`
- 默认账号：`admin / admin123`

---

### B. Linux + Gunicorn 快速上线

```bash
# 1) 进入项目目录
cd /path/to/gallery_site

# 2) 安装依赖
pip install -r requirements.txt

# 3) 设置生产密钥（建议）
export SECRET_KEY="replace-with-a-strong-random-string"

# 4) 启动 Gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

然后用 Nginx 反代到 5000 端口并配置 HTTPS（推荐）。

#### Nginx 最小可用配置示例

将以下内容保存到（示例）：`/etc/nginx/sites-available/gallery`，并软链接到 `sites-enabled`。

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 500m;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

应用配置：

```bash
sudo nginx -t
sudo systemctl reload nginx
```

> 如需 HTTPS，建议使用 Certbot：
>
> `sudo certbot --nginx -d your-domain.com`

---

### C. Railway 一键部署

1. 将项目推到 Git 仓库并导入 Railway
2. 启动命令填写：

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

3. 添加环境变量：

- `SECRET_KEY=你的强随机字符串`

4. 部署成功后打开域名访问

---

### D. 上线后第一件事（强烈建议）

- 立即修改后台默认账号密码
- 先做一次“数据备份”
- 若在容器平台部署（如 Railway），务必配置持久化卷或定期备份恢复

---

## 1. 项目功能总览

### 前台页面

- 首页（瀑布流）
  - 分类筛选、排序（最新/最早/点赞）
  - 无限滚动分页加载
  - 点赞
  - 图片 / 视频 / 3D（`.glb/.gltf`）预览弹窗
  - 预览内支持：
    - PC 滚轮上下切换上一条/下一条
    - 移动端上滑/下滑切换上一条/下一条
    - 移动端返回键优先关闭预览
- 橱窗精选（Showcase）
  - 可配置展示、自动滚动、点赞
  - 支持图片/视频/3D
- 详情精选（Featured）
  - 图集式展示与查看器
- 关于我页面
  - 个人简介（支持富文本）
  - 技能、社交链接
  - 近期作品预览（支持图片/视频/3D）
- 留言板页面
  - 访客留言、回复
  - 头像上传与配额限制
  - 近期作品预览（支持图片/视频/3D）
- 电子木鱼页面（可选玩法模块）

### 后台管理

- 登录鉴权
- 内容管理
  - 新增/编辑/删除作品
  - 批量删除
  - 排序
  - 替换原文件/封面
  - 点赞数手动调整并保存
- 分类管理
- 橱窗精选管理
- 详情精选管理
- 留言管理（审核、回复、删除）
- 访客记录
  - 记录 IP、访问路径、UA、来源
  - 自动解析地区（多源容错）
- 站点配置
  - 基础信息、导航、Hero、Footer、About、留言页配置
  - 主题配置
- 媒体管理
  - 上传、替换、清理未引用文件
  - 缩略图检查/补全/重建
- 数据备份与恢复
  - 备份包含所有 `data/*.json`
  - 支持 `uploads/` 与 `thumbs/` 一并备份/恢复

---

## 2. 技术栈与必要组件

- Python 3.10+（建议 3.11/3.12）
- Flask
- Gunicorn（生产环境 WSGI）
- Pillow（图片处理与缩略图）

依赖见 `requirements.txt`：

- `flask>=2.3.0`
- `werkzeug>=2.3.0`
- `gunicorn>=21.0.0`
- `Pillow>=10.0.0`

---

## 3. 本地开发与运行

### 3.1 安装依赖

```bash
pip install -r requirements.txt
```

### 3.2 启动项目

```bash
python app.py
```

启动后访问：

- 前台首页：`http://localhost:5000`
- 后台登录：`http://localhost:5000/admin/login`

默认后台账号：

- 用户名：`admin`
- 密码：`admin123`

> 建议首次登录后立即修改账号密码。

---

## 4. 目录结构（核心）

```text
gallery_site/
├─ app.py                  # Flask 主程序与所有路由
├─ requirements.txt        # Python 依赖
├─ data/                   # 动态数据（JSON）
│  ├─ content.json         # 作品数据
│  ├─ site.json            # 站点配置
│  ├─ messages.json        # 留言数据
│  ├─ visitors.json        # 访客记录
│  ├─ likes.json           # 点赞数据
│  ├─ showcase.json        # 橱窗精选
│  ├─ featured.json        # 详情精选
│  ├─ auth.json            # 后台账号
│  ├─ smtp.json            # SMTP配置
│  ├─ emoji.json / muyu.json
│  └─ ...
├─ static/
│  ├─ uploads/             # 原始上传文件
│  └─ thumbs/              # 缩略图
└─ templates/
   ├─ index.html           # 首页
   ├─ admin.html           # 后台
   ├─ about.html           # 关于我
   ├─ messages.html        # 留言板
   └─ ...
```

---

## 5. 部署方法

## 5.1 通用 Python 服务器（Linux）

1. 安装 Python 与依赖
2. 安装项目依赖
3. 用 Gunicorn 启动

示例：

```bash
pip install -r requirements.txt
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

可选：配合 Nginx 做反向代理与 HTTPS。

### 5.2 Railway 部署

可直接部署 Python 项目，启动命令可用：

```bash
gunicorn -w 2 -b 0.0.0.0:$PORT app:app
```

**重要：数据持久化说明**

项目数据与媒体默认保存在本地文件系统（`data/`、`static/uploads/`、`static/thumbs/`）。
在 Railway 等容器平台中，重新部署可能导致数据丢失。建议：

- 挂载持久化卷（Volume），或
- 定期使用后台“数据备份”导出，再在新环境恢复

---

## 6. 配置项与环境变量

- `SECRET_KEY`（可选，强烈建议生产环境设置）
  - 用于 Flask Session 签名
  - 未设置时会使用代码中的默认值（生产不建议）

Windows PowerShell 示例：

```powershell
$env:SECRET_KEY="replace-with-a-strong-random-string"
python app.py
```

Linux/macOS 示例：

```bash
export SECRET_KEY="replace-with-a-strong-random-string"
python app.py
```

---

## 7. 使用说明（后台）

1. 登录后台
2. 在“内容管理”新增作品：
   - 支持图片、视频、3D 文件
   - 可上传封面
3. 在“站点配置”调整主题、导航、海报、页脚、关于我信息
4. 在“橱窗精选/详情精选”配置首页重点内容
5. 在“留言管理”审核与回复留言
6. 在“数据备份”导出完整动态数据（可选附带媒体与缩略图）

---

## 8. 常见问题

### Q1：3D 预览打不开

- 确认文件后缀为 `.glb` 或 `.gltf`
- 确认文件实际存在于 `static/uploads/`
- 若历史数据 `type` 字段错误，执行历史数据修复

### Q2：访客地区不显示

- 本地私网 IP（如 `127.0.0.1`、`192.168.x.x`）无法解析真实地理位置
- 在线部署依赖外部 IP 地区接口，若网络受限可能返回空

### Q3：重新部署后数据丢失

- 属于容器临时文件系统现象
- 使用持久化卷，或先备份再恢复

---

## 9. 安全建议（生产）

- 立即修改默认后台账号密码
- 配置强随机 `SECRET_KEY`
- 后台建议仅内网可访问或加额外鉴权
- 定期备份 `data/` 与媒体文件

---

## 10. 许可证

当前仓库未显式声明 LICENSE。如需开源分发，请补充许可证文件。