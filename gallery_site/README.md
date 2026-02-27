# GALLERY · 视觉创作集

一个 Pinterest 风格的图片/视频展示网站，支持瀑布流布局、后台管理、留言板等功能。

---

## 项目结构

```
gallery_site/
├── app.py                 # Flask 后端主程序
├── requirements.txt       # Python 依赖
├── templates/
│   ├── index.html         # 前台展示页
│   └── admin.html         # 后台管理页
├── static/
│   └── uploads/           # 上传文件存储目录（自动创建）
└── data/
    ├── content.json       # 内容数据（自动创建）
    └── messages.json      # 留言数据（自动创建）
```

---

## 快速开始

### 1. 安装 Python 依赖

```bash
# 推荐使用虚拟环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 运行服务

```bash
python app.py
```

### 3. 访问网站

- **前台展示**：http://localhost:5000
- **后台管理**：http://localhost:5000/admin

---

## 功能说明

### 前台页面
| 功能 | 说明 |
|------|------|
| 顶部导航 | 分类筛选、联系方式、自我介绍、留言板 |
| 轮播海报 | 3 张精选海报，支持自动播放和手动切换 |
| 分类筛选栏 | 点击分类标签过滤内容 |
| 瀑布流展示 | Pinterest 风格自适应瀑布流，支持懒加载 |
| 无限滚动 | 滚动到底部自动加载更多内容 |
| 图片/视频预览 | 点击卡片弹出大图/视频播放 |
| 关于我 | 个人介绍区块 |
| 联系方式 | 联系信息卡片 |
| 留言板 | 访客留言提交与展示 |

### 后台管理 (`/admin`)
| 功能 | 说明 |
|------|------|
| 仪表盘 | 数据统计概览 |
| 上传内容 | 支持拖拽上传图片/视频，填写标题、分类、描述 |
| 内容管理 | 查看所有作品，一键删除 |
| 分类管理 | 添加/删除分类标签 |
| 留言管理 | 查看并删除访客留言 |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/items?page=1&per_page=20&category=摄影` | 获取内容列表 |
| GET | `/api/categories` | 获取分类列表 |
| GET/POST | `/api/messages` | 获取/发送留言 |
| POST | `/admin/upload` | 上传文件（multipart/form-data） |
| DELETE | `/admin/delete/<id>` | 删除内容 |
| POST | `/admin/categories` | 管理分类 |

---

## 自定义配置

编辑 `app.py` 顶部的常量：
- `UPLOAD_FOLDER`：上传文件目录
- `app.config['MAX_CONTENT_LENGTH']`：最大上传文件大小（默认 500MB）
- `app.secret_key`：Flask session 密钥（生产环境请更换）

---

## 生产部署建议

```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

建议在前面配置 Nginx 处理静态文件，并使用 HTTPS。

---

## 技术栈

- **后端**：Python 3 + Flask
- **数据存储**：JSON 文件（content.json, messages.json）
- **前端**：原生 HTML5 + CSS3 + JavaScript（无框架依赖）
- **布局**：CSS `columns` 实现瀑布流
- **懒加载**：`IntersectionObserver` API
- **字体**：Google Fonts（Playfair Display + Noto Sans SC + Cormorant Garamond）
