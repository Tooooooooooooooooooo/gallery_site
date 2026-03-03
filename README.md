# Gallery CMS

个人作品集 CMS，基于 Flask。

## 本地运行

```bash
pip install -r requirements.txt
python app.py
```

访问 http://localhost:5000，后台 http://localhost:5000/admin/login  
默认账号：admin / admin123

## Railway 部署注意

- 数据文件（data/*.json）和上传文件（static/uploads/）存储在容器本地  
- Railway 每次重新部署会**重置**文件系统，数据会丢失  
- 建议挂载 Railway Volume 或使用外部存储持久化数据
或部署前备份网站数据，重新部署后一键恢复全部数据