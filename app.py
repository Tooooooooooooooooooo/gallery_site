from flask import Flask, render_template, request, jsonify, session, redirect
from functools import wraps
import json, os, uuid, hashlib, smtplib, secrets, time
import urllib.request, urllib.parse, mimetypes
import zipfile, tempfile, shutil, io
try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'gallery-secret-key-2024-x9z')

# 基于 app.py 所在目录的绝对路径，避免 gunicorn 工作目录不一致问题
_BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(_BASE, 'static', 'uploads')
THUMBS_FOLDER = os.path.join(_BASE, 'static', 'thumbs')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'webm', 'glb', 'gltf'}
IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
DATA_FILE     = os.path.join(_BASE, 'data', 'content.json')
MESSAGES_FILE = os.path.join(_BASE, 'data', 'messages.json')
SITE_FILE     = os.path.join(_BASE, 'data', 'site.json')
VISITORS_FILE = os.path.join(_BASE, 'data', 'visitors.json')
LIKES_FILE    = os.path.join(_BASE, 'data', 'likes.json')
AUTH_FILE     = os.path.join(_BASE, 'data', 'auth.json')
SMTP_FILE     = os.path.join(_BASE, 'data', 'smtp.json')

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

def make_thumb(src_filename, scale_pct=50):
    """从 uploads 里的图片生成缩图，存到 thumbs 目录，返回缩图文件名"""
    if not HAS_PIL:
        return None
    if not src_filename:
        return None
    if src_filename.startswith('http://') or src_filename.startswith('https://'):
        return None  # 外链不生成缩图
    src = os.path.join(UPLOAD_FOLDER, src_filename)
    if not os.path.exists(src):
        return None
    try:
        with Image.open(src) as img:
            # 保持 EXIF 方向
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            w, h = img.size
            scale = max(10, min(100, int(scale_pct))) / 100
            nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
            img_resized = img.resize((nw, nh), Image.LANCZOS)
            # 缩图文件名：thumb_ 前缀 + 原名（保留 jpg/png/webp）
            base, ext = os.path.splitext(src_filename)
            ext = ext.lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
                ext = '.jpg'
            thumb_name = 'thumb_' + base + ext
            thumb_path = os.path.join(THUMBS_FOLDER, thumb_name)
            fmt = 'JPEG' if ext in ('.jpg', '.jpeg') else ('PNG' if ext == '.png' else 'WEBP')
            if fmt == 'JPEG' and img_resized.mode in ('RGBA', 'LA', 'P'):
                img_resized = img_resized.convert('RGB')
            img_resized.save(thumb_path, fmt, quality=82, optimize=True)
            return thumb_name
    except Exception as e:
        print(f'make_thumb error: {e}')
        return None

def allowed_file(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def allowed_img(f): return '.' in f and f.rsplit('.', 1)[1].lower() in IMG_EXTENSIONS
def is_video(f):
    if not f or '.' not in f: return False
    ext = f.rsplit('.', 1)[1].lower().split('?')[0]
    return ext in {'mp4', 'mov', 'webm'}

def is_model(f):
    if not f or '.' not in f: return False
    ext = f.rsplit('.', 1)[1].lower().split('?')[0]
    return ext in {'glb', 'gltf'}
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_data(): return load_json(DATA_FILE, {"items": [], "categories": ["摄影", "插画", "设计", "视频", "其他"]})
def save_data(d): save_json(DATA_FILE, d)
def load_messages(): return load_json(MESSAGES_FILE, [])
def save_messages(d): save_json(MESSAGES_FILE, d)
def load_visitors(): return load_json(VISITORS_FILE, [])
def save_visitors(d): save_json(VISITORS_FILE, d)
def load_likes(): return load_json(LIKES_FILE, {})
def save_likes(d): save_json(LIKES_FILE, d)
def load_auth():
    d = load_json(AUTH_FILE, {"username": "admin", "password": hash_pw("admin123")})
    d.setdefault("email", "")
    d.setdefault("avatar", "")
    return d

def load_smtp():
    return load_json(SMTP_FILE, {
        "host": "", "port": 465, "user": "", "password": "",
        "use_ssl": True, "from_name": "Gallery Admin"
    })

def save_smtp(d): save_json(SMTP_FILE, d)

# 验证码临时存储（内存，重启失效）
_reset_codes = {}  # email -> {code, expires}

# 头像上传计数（内存，重启清零） key: "ip:YYYY-MM-DD" -> count
_avatar_upload_counts = {}

def send_reset_email(to_email, code):
    cfg = load_smtp()
    if not cfg.get('host') or not cfg.get('user'):
        raise ValueError("SMTP 未配置")
    body = f"Gallery 管理后台密码重置验证码：{code}\n\n验证码10分钟内有效，如非本人操作请忽略。"
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header('Gallery 密码重置验证码', 'utf-8')
    msg['From'] = formataddr((str(Header(cfg.get('from_name','Gallery'), 'utf-8')), cfg['user']))
    msg['To'] = to_email
    _smtp_send(cfg, msg)

def _smtp_send(cfg, msg):
    port = int(cfg.get('port', 465))
    use_ssl = cfg.get('use_ssl', True)
    if use_ssl:
        with smtplib.SMTP_SSL(cfg['host'], port, timeout=15) as s:
            s.login(cfg['user'], cfg['password'])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg['host'], port, timeout=15) as s:
            s.ehlo(); s.starttls(); s.login(cfg['user'], cfg['password'])
            s.send_message(msg)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

def get_default_site():
    return {
        "site": {"title": "GALLERY · 视觉创作集", "subtitle": "记录生活之美，分享视觉灵感", "favicon": "", "model_hint": "🖱️ 左键旋转 · 滚轮缩放 · 右键平移", "model_hint_position": "bottom", "model_hint_bg": "rgba(0,0,0,.52)", "model_hint_color": "rgba(255,255,255,.92)", "model_hint_font_size": 12, "model_hint_max_width": 900, "model_hint_radius": 10},
        "theme": "warm",
        "thumb_scale": 50,
        "nav": {
            "logo": "GAL·LERY",
            "links": [
                {"label": "分类", "href": "#gallery"},
                {"label": "关于我", "href": "/about"},
                {"label": "留言板", "href": "/messages"}
            ]
        },
        "hero": {
            "enabled": True,
            "height": 540,
            "slides": [
                {"id": "s1", "tag": "Featured Collection", "title": "光与影的<br>艺术对话",
                 "subtitle": "探索每一帧背后的故事，感受视觉创作的无限可能",
                 "btnText": "浏览作品", "btnHref": "#gallery",
                 "bgType": "gradient", "bgValue": "linear-gradient(135deg, #2c1810 0%, #8b4513 40%, #d4896a 100%)"},
                {"id": "s2", "tag": "New Arrivals", "title": "自然之美<br>无处不在",
                 "subtitle": "每一张照片都是一次与世界的亲密相遇",
                 "btnText": "查看最新", "btnHref": "#gallery",
                 "bgType": "gradient", "bgValue": "linear-gradient(135deg, #0d1b2a 0%, #1b4332 40%, #40916c 100%)"},
                {"id": "s3", "tag": "Creative Space", "title": "创意无界<br>灵感涌现",
                 "subtitle": "分享你看见的世界，让创作连接彼此",
                 "btnText": "留下足迹", "btnHref": "/messages",
                 "bgType": "gradient", "bgValue": "linear-gradient(135deg, #1a0533 0%, #6b21a8 40%, #c084fc 100%)"}
            ]
        },
        "about": {
            "heroImage": "", "avatarImage": "",
            "name": "创作者", "tagline": "用镜头记录世界的美好", "emoji": "🎨",
            "paragraphs": [
                "你好，我是这个画廊的主人。我热爱用镜头和画笔记录生活中的美好瞬间。",
                "这里汇聚了我在摄影、插画、设计等领域的探索与实践。",
                "我相信，美无处不在，关键在于是否有一双发现美的眼睛。"
            ],
            "skills": [{"label": "摄影", "icon": "", "value": 90}, {"label": "插画", "icon": "", "value": 75}, {"label": "设计", "icon": "", "value": 80}],
            "socials": [
                {"label": "微博", "icon": "", "href": "#", "hover_image": "", "hover_w": 220, "hover_h": 140},
                {"label": "Instagram", "icon": "", "href": "#", "hover_image": "", "hover_w": 220, "hover_h": 140},
                {"label": "小红书", "icon": "", "href": "#", "hover_image": "", "hover_w": 220, "hover_h": 140}
            ]
        },
        "messages_page": {
            "bgType": "gradient",
            "bgValue": "linear-gradient(135deg, #1a1208 0%, #3d2510 50%, #6b3d18 100%)",
            "title": "留言板",
            "subtitle": "留下你的足迹，与我分享你的想法",
            "defaultAvatar": "",
            "avatarPool": []
        },
        "footer": {
            "brand": {"logo": "GAL·LERY", "desc": "记录生活之美，分享视觉灵感。\n每一帧都是独一无二的故事。"},
            "columns": [
                {"title": "导航", "image": "", "links": [
                    {"label": "作品集", "href": "#gallery"}, {"label": "关于我", "href": "/about"},
                    {"label": "留言板", "href": "/messages"}, {"label": "管理后台", "href": "/admin"}
                ]},
                {"title": "关于", "image": "", "links": [
                    {"label": "隐私政策", "href": "#"}, {"label": "版权声明", "href": "#"}
                ]}
            ],
            "copyright": "© 2024 GALLERY · 视觉创作集. All Rights Reserved. · Made with ♥"
        }
    }

def load_site():
    d = load_json(SITE_FILE, None)
    if d is None: return get_default_site()
    default = get_default_site()
    for key in default:
        if key not in d: d[key] = default[key]
    if 'site' in d:
        for k, v in default['site'].items():
            if k not in d['site']:
                d['site'][k] = v
    if 'about' in d:
        for k, v in default['about'].items():
            if k not in d['about']: d['about'][k] = v
    if 'messages_page' not in d: d['messages_page'] = default['messages_page']
    if 'footer' not in d: d['footer'] = default['footer']
    else:
        d['footer'].setdefault('brand', default['footer']['brand'])
        d['footer'].setdefault('columns', default['footer']['columns'])
        d['footer'].setdefault('copyright', default['footer']['copyright'])
        for c in d['footer'].get('columns', []):
            if 'image' not in c:
                c['image'] = ''
    if 'theme' not in d: d['theme'] = 'warm'
    if 'thumb_scale' not in d: d['thumb_scale'] = 50
    if 'enabled' not in d.get('hero', {}): d['hero']['enabled'] = True
    return d

def save_site(d): save_json(SITE_FILE, d)

def save_upload(file, prefix=''):
    ext = file.filename.rsplit('.', 1)[1].lower()
    fn = prefix + str(uuid.uuid4()) + '.' + ext
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    return fn

# IP region memory cache
_ip_region_cache = {}

def _get_real_ip():
    """从请求头取真实 IP（Railway/Nginx 反向代理后在 X-Forwarded-For）"""
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    return request.remote_addr or "unknown"

def _is_private_ip(ip):
    return (not ip or ip in ("unknown", "127.0.0.1", "::1")
            or ip.startswith("192.168.") or ip.startswith("10.")
            or ip.startswith("172.16.") or ip.startswith("172.17.")
            or ip.startswith("172.18.") or ip.startswith("172.19.")
            or ip.startswith("172.2") or ip.startswith("172.3"))

def _lookup_ip_region(ip):
    if _is_private_ip(ip):
        return ""
    if ip in _ip_region_cache:
        return _ip_region_cache[ip]
    try:
        import urllib.request as _ur, json as _js

        def _from_ip_api():
            url = "http://ip-api.com/json/" + ip + "?lang=zh-CN&fields=status,country,regionName,city"
            req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=3) as resp:
                return _js.loads(resp.read())

        def _from_ipapi_co():
            # 备用：ipapi.co，返回英文字段
            url = "https://ipapi.co/" + ip + "/json/"
            req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=4) as resp:
                return _js.loads(resp.read())

        region = ""
        d = {}
        try:
            d = _from_ip_api()
        except Exception:
            # ip-api.com 不可用时，再尝试备用接口
            try:
                d = _from_ipapi_co()
            except Exception:
                d = {}

        if d:
            # ip-api.com 格式
            if d.get("status") == "success":
                parts = [d.get("country",""), d.get("regionName",""), d.get("city","")]
            else:
                # ipapi.co 等备用格式
                parts = [d.get("country_name",""), d.get("region",""), d.get("city","")]
            seen, out = set(), []
            for p in parts:
                if p and p not in seen:
                    seen.add(p); out.append(p)
            region = " ".join(out)

        _ip_region_cache[ip] = region or ""
        return region or ""
    except Exception:
        return ""

def record_visitor():
    import threading
    from datetime import timedelta
    ip = _get_real_ip()
    v = {"id": str(uuid.uuid4()),
         "time": (datetime.utcnow() + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S"),
         "ip": ip, "region": "",
         "ua": request.headers.get("User-Agent", "")[:200],
         "path": request.path, "referer": request.referrer or ""}
    visitors = load_visitors()
    visitors.insert(0, v)
    if len(visitors) > 2000:
        visitors = visitors[:2000]
    save_visitors(visitors)

    def _fill_region(vid, vip):
        region = _lookup_ip_region(vip)
        if not region:
            return
        vs = load_visitors()
        for item in vs:
            if item.get("id") == vid:
                item["region"] = region
                break
        save_visitors(vs)
    threading.Thread(target=_fill_region, args=(v["id"], ip), daemon=True).start()

# ── Auth Routes ──
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        body = request.json or {}
        auth = load_auth()
        if body.get('username') == auth['username'] and hash_pw(body.get('password', '')) == auth['password']:
            session['logged_in'] = True
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': '用户名或密码错误'}), 401
    if session.get('logged_in'): return redirect('/admin')
    return render_template('login.html')

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/admin/change-password', methods=['PUT'])
@login_required
def admin_change_password():
    body = request.json
    auth = load_auth()
    if hash_pw(body.get('oldPassword', '')) != auth['password']:
        return jsonify({'success': False, 'error': '原密码错误'}), 400
    auth['username'] = body.get('username', auth['username'])
    auth['password'] = hash_pw(body.get('newPassword', ''))
    save_json(AUTH_FILE, auth)
    return jsonify({'success': True})

# ── Public Routes ──
@app.route('/')
def index():
    record_visitor()
    return render_template('index.html')

@app.route('/about')
def about_page():
    record_visitor()
    return render_template('about.html')

@app.route('/messages')
def messages_page():
    record_visitor()
    return render_template('messages.html')

@app.route('/api/site')
def api_site():
    return jsonify(load_site())

@app.route('/api/items')
def api_items():
    data = load_data()
    likes = load_likes()
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    categories = request.args.getlist('category')
    sort = request.args.get('sort', 'newest')
    items = data['items']
    if categories:
        items = [i for i in items if any(c in (i.get('categories') or [i.get('category','')]) for c in categories)]
    if sort == 'likes':
        items = sorted(items, key=lambda i: likes.get(i['id'], 0), reverse=True)
    elif sort == 'oldest':
        items = sorted(items, key=lambda i: i.get('created_at', ''))
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = [dict(i) for i in items[start:end]]
    for item in page_items:
        fn = item.get('filename', '')
        item['type'] = 'model' if is_model(fn) else ('video' if is_video(fn) else item.get('type', 'image'))
        item['likes'] = likes.get(item['id'], 0)
    return jsonify({'items': page_items, 'total': total, 'page': page, 'has_more': end < total})

@app.route('/api/categories')
def api_categories():
    return jsonify(load_data().get('categories', []))

@app.route('/api/avatar-upload', methods=['POST'])
def api_avatar_upload():
    """记录并校验头像上传次数（以 IP 为单位，每日限制）"""
    from datetime import date
    site = load_site()
    mp = site.get('messages_page', {})
    daily_limit = int(mp.get('avatarDailyLimit', 0))  # 0 = 不限制
    ip = request.remote_addr or 'unknown'
    today = str(date.today())
    key = f"{ip}:{today}"
    count = _avatar_upload_counts.get(key, 0)
    if daily_limit > 0 and count >= daily_limit:
        return jsonify({'success': False, 'error': f'今日头像上传次数已达上限（{daily_limit} 次）', 'count': count, 'limit': daily_limit}), 429
    _avatar_upload_counts[key] = count + 1
    return jsonify({'success': True, 'count': count + 1, 'limit': daily_limit, 'remaining': max(0, daily_limit - count - 1) if daily_limit > 0 else -1})

@app.route('/api/avatar-upload-status', methods=['GET'])
def api_avatar_upload_status():
    """查询当前 IP 今日头像上传次数"""
    from datetime import date
    site = load_site()
    mp = site.get('messages_page', {})
    daily_limit = int(mp.get('avatarDailyLimit', 0))
    ip = request.remote_addr or 'unknown'
    today = str(date.today())
    key = f"{ip}:{today}"
    count = _avatar_upload_counts.get(key, 0)
    return jsonify({'count': count, 'limit': daily_limit, 'remaining': max(0, daily_limit - count) if daily_limit > 0 else -1})

@app.route('/api/messages', methods=['GET', 'POST'])
def api_messages():
    if request.method == 'POST':
        body = request.json
        messages = load_messages()
        msg = {'id': str(uuid.uuid4()), 'name': body.get('name', '匿名'), 'avatar': body.get('avatar', ''),
               'content': body.get('content', ''), 'time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'approved': False}
        messages.insert(0, msg)
        save_messages(messages)
        return jsonify({'success': True, 'message': msg})
    return jsonify([m for m in load_messages() if m.get('approved', True)])

@app.route('/api/messages/<msg_id>/reply', methods=['POST'])
def api_reply_message(msg_id):
    messages = load_messages()
    body = request.json or {}
    for m in messages:
        if m['id'] == msg_id:
            if 'replies' not in m:
                m['replies'] = []
            reply = {
                'id': str(uuid.uuid4()),
                'name': body.get('name', '匿名'),
                'content': body.get('content', ''),
                'avatar': body.get('avatar', ''),
                'time': datetime.now().strftime('%Y-%m-%d %H:%M')
            }
            m['replies'].append(reply)
            save_messages(messages)
            return jsonify({'success': True, 'reply': reply})
    return jsonify({'success': False, 'error': '留言不存在'}), 404

# IP 点赞状态（内存，重启清零）key: "ip:item_id" -> True/False
def _ip_key(ip, item_id):
    return f"ip:{ip}:{item_id}"

def ip_like_toggle(item_id, ip):
    """切换点赞状态并持久化，返回 (is_liked_after, delta)"""
    likes = load_likes()
    key = _ip_key(ip, item_id)
    currently = likes.get(key, False)
    likes[key] = not currently
    save_likes(likes)
    return not currently, (1 if not currently else -1)

@app.route('/api/like/<item_id>', methods=['POST'])
def api_like(item_id):
    ip = request.remote_addr or 'unknown'
    likes = load_likes()
    key = _ip_key(ip, item_id)
    currently = likes.get(key, False)
    is_liked = not currently
    likes[key] = is_liked
    likes[item_id] = max(0, likes.get(item_id, 0) + (1 if is_liked else -1))
    save_likes(likes)
    return jsonify({'success': True, 'liked': is_liked, 'likes': likes[item_id]})

@app.route('/api/liked-status')
def api_liked_status():
    """返回当前 IP 对指定 item 列表的点赞状态"""
    ip = request.remote_addr or 'unknown'
    ids = request.args.get('ids', '').split(',')
    likes = load_likes()
    result = {item_id: bool(likes.get(_ip_key(ip, item_id), False)) for item_id in ids if item_id}
    return jsonify(result)

# ── Admin Routes (protected) ──

@app.route('/admin')
@login_required
def admin():
    return render_template('admin.html')

@app.route('/admin/upload', methods=['POST'])
@login_required
def admin_upload():
    data = load_data()
    file = request.files.get('file')
    cover = request.files.get('cover')
    existing_file = request.form.get('existing_file', '')
    existing_cover = request.form.get('existing_cover', '')
    if not file and not existing_file:
        return jsonify({'success': False, 'error': '无效文件'}), 400
    if file:
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '无效文件'}), 400
        filename = save_upload(file)
    else:
        filename = existing_file
    cover_filename = None
    if cover and allowed_img(cover.filename):
        cover_filename = save_upload(cover, 'cover_')
    elif existing_cover:
        cover_filename = existing_cover
    likes = load_likes()
    item_id = str(uuid.uuid4())
    cats = request.form.getlist('categories')
    if not cats:
        c = request.form.get('category', '其他')
        cats = [c] if c else ['其他']
    item = {
        'id': item_id, 'title': request.form.get('title', ''),
        'categories': cats, 'category': cats[0] if cats else '其他',
        'description': request.form.get('description', ''),
        'filename': filename, 'cover': cover_filename,
        'type': 'model' if is_model(filename) else ('video' if is_video(filename) else 'image'),
        'thumb': None,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'width': int(request.form.get('width', 800)),
        'height': int(request.form.get('height', 600)),
        'sort_order': int(request.form.get('sort_order', 0)),
    }
    likes[item_id] = max(0, int(request.form.get('likes', 0)))
    save_likes(likes)
    data['items'].insert(0, item)
    # 自动生成缩图（仅图片）
    if (not is_video(filename)) and (not is_model(filename)):
        scale = load_site().get('thumb_scale', 50)
        src_fn = cover_filename if cover_filename else filename
        thumb_fn = make_thumb(src_fn, scale)
        if thumb_fn:
            item['thumb'] = thumb_fn
    save_data(data)
    return jsonify({'success': True, 'item': item})

@app.route('/admin/item/<item_id>', methods=['PUT'])
@login_required
def admin_edit_item(item_id):
    data = load_data()
    body = request.json
    for item in data['items']:
        if item['id'] == item_id:
            item['title'] = body.get('title', item.get('title', ''))
            cats = body.get('categories', None)
            if cats is not None:
                item['categories'] = cats
                item['category'] = cats[0] if cats else '其他'
            item['description'] = body.get('description', item.get('description', ''))
            item['width'] = int(body.get('width', item.get('width', 800)))
            item['height'] = int(body.get('height', item.get('height', 600)))
            item['sort_order'] = int(body.get('sort_order', item.get('sort_order', 0)))
            if 'likes' in body:
                likes = load_likes()
                likes[item_id] = max(0, int(body['likes']))
                save_likes(likes)
            break
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/items/reorder', methods=['PUT'])
@login_required
def admin_reorder_items():
    data = load_data()
    body = request.json
    order = body.get('order', [])
    id_to_order = {oid: idx for idx, oid in enumerate(order)}
    for item in data['items']:
        if item['id'] in id_to_order:
            item['sort_order'] = id_to_order[item['id']]
    data['items'].sort(key=lambda i: i.get('sort_order', 9999))
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/items/bulk-delete', methods=['POST'])
@login_required
def admin_bulk_delete():
    data = load_data()
    ids = set(request.json.get('ids', []))
    data['items'] = [i for i in data['items'] if i['id'] not in ids]
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/item/<item_id>/replace-file', methods=['POST'])
@login_required
def admin_replace_file(item_id):
    data = load_data()
    file = request.files.get('file')
    existing = request.form.get('existing_file', '')
    if file and allowed_file(file.filename):
        filename = save_upload(file)
    elif existing:
        filename = existing
    else:
        return jsonify({'success': False, 'error': '无效文件'}), 400
    for item in data['items']:
        if item['id'] == item_id:
            item['filename'] = filename
            item['type'] = 'model' if is_model(filename) else ('video' if is_video(filename) else 'image')
            break
    save_data(data)
    return jsonify({'success': True, 'filename': filename})

@app.route('/admin/item/<item_id>/replace-cover', methods=['POST'])
@login_required
def admin_replace_cover(item_id):
    data = load_data()
    file = request.files.get('file')
    existing = request.form.get('existing_file', '')
    if file and allowed_img(file.filename):
        cover_filename = save_upload(file, 'cover_')
    elif existing:
        cover_filename = existing
    else:
        return jsonify({'success': False, 'error': '无效图片'}), 400
    for item in data['items']:
        if item['id'] == item_id:
            item['cover'] = cover_filename
            break
    save_data(data)
    return jsonify({'success': True, 'cover': cover_filename})

@app.route('/admin/delete/<item_id>', methods=['DELETE'])
@login_required
def admin_delete(item_id):
    data = load_data()
    item = next((i for i in data['items'] if i['id'] == item_id), None)
    if item:
        data['items'] = [i for i in data['items'] if i['id'] != item_id]
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/categories', methods=['POST'])
@login_required
def admin_categories():
    data = load_data()
    body = request.json
    action = body.get('action')
    cat = body.get('category', '').strip()
    if action == 'add' and cat and cat not in data['categories']:
        data['categories'].append(cat)
    elif action == 'remove' and cat in data['categories']:
        data['categories'].remove(cat)
    elif action == 'reorder':
        new_order = body.get('categories', [])
        # 只接受已存在的分类，防止注入
        valid = [c for c in new_order if c in data['categories']]
        # 补上未出现的（容错）
        rest = [c for c in data['categories'] if c not in valid]
        data['categories'] = valid + rest
    save_data(data)
    return jsonify({'success': True, 'categories': data['categories']})

@app.route('/admin/messages')
@login_required
def admin_messages_list():
    return jsonify(load_messages())

@app.route('/admin/messages/replies/<msg_id>', methods=['PUT'])
@login_required
def admin_update_replies(msg_id):
    messages = load_messages()
    body = request.json or {}
    for m in messages:
        if m['id'] == msg_id:
            m['replies'] = body.get('replies', [])
            save_messages(messages)
            return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/admin/messages/approve/<msg_id>', methods=['PUT'])
@login_required
def admin_approve_message(msg_id):
    messages = load_messages()
    for m in messages:
        if m['id'] == msg_id:
            m['approved'] = not m.get('approved', False)
            break
    save_messages(messages)
    return jsonify({'success': True})

@app.route('/admin/messages/delete/<msg_id>', methods=['DELETE'])
@login_required
def admin_delete_message(msg_id):
    save_messages([m for m in load_messages() if m['id'] != msg_id])
    return jsonify({'success': True})

@app.route('/admin/likes/recent')
@login_required
def admin_recent_likes():
    likes = load_likes()
    data = load_data()
    id_to_item = {i['id']: i for i in data['items']}
    result = []
    for item_id, count in sorted(likes.items(), key=lambda x: -x[1])[:10]:
        if count > 0 and item_id in id_to_item:
            item = id_to_item[item_id]
            result.append({'id': item_id, 'title': item.get('title', '(无标题)'), 'likes': count,
                           'cover': item.get('cover') or (item.get('filename') if item.get('type') != 'video' else None)})
    return jsonify(result)

@app.route('/admin/visitors')
@login_required
def admin_visitors():
    visitors = load_visitors()
    page = int(request.args.get('page', 1))
    per_page = 50
    path_filter = (request.args.get('path', '') or '').strip()
    from collections import Counter
    from datetime import timedelta

    filtered = visitors
    if path_filter:
        filtered = [v for v in visitors if (v.get('path') or '') == path_filter]

    start = (page - 1) * per_page
    end = start + per_page

    paths = Counter(v.get('path', '') for v in filtered)
    ips = Counter(v.get('ip', '') for v in filtered)
    today = datetime.now().date()
    daily = {}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).strftime('%m-%d')
        daily[d] = 0
    for v in filtered:
        try:
            k = v['time'][5:10]
            if k in daily: daily[k] += 1
        except: pass
    # 异步补全没有 region 的记录
    import threading
    def _backfill():
        vs = load_visitors()
        changed = False
        for item in vs[:100]:  # 只补最近100条
            if item.get("region") is None or item.get("region") == "":
                ip = item.get("ip","")
                if not _is_private_ip(ip):
                    region = _lookup_ip_region(ip)
                    if region:
                        item["region"] = region
                        changed = True
        if changed:
            save_visitors(vs)
    threading.Thread(target=_backfill, daemon=True).start()
    return jsonify({'total': len(filtered), 'visitors': filtered[start:end],
                    'has_more': end < len(filtered), 'page': page,
                    'top_pages': paths.most_common(10), 'top_ips': ips.most_common(10),
                    'daily': list(daily.items())})

@app.route('/admin/visitors/clear', methods=['DELETE'])
@login_required
def admin_clear_visitors():
    save_visitors([])
    return jsonify({'success': True})

# Site config (all protected)
@app.route('/admin/site/basic', methods=['PUT'])
@login_required
def admin_site_basic():
    site = load_site()
    body = request.json
    if 'site' not in site: site['site'] = {}
    site['site']['title'] = body.get('title', site['site'].get('title', ''))
    site['site']['subtitle'] = body.get('subtitle', site['site'].get('subtitle', ''))
    site['site']['model_hint'] = body.get('model_hint', site['site'].get('model_hint', ''))
    site['site']['model_hint_position'] = body.get('model_hint_position', site['site'].get('model_hint_position', 'bottom'))
    site['site']['model_hint_bg'] = body.get('model_hint_bg', site['site'].get('model_hint_bg', 'rgba(0,0,0,.52)'))
    site['site']['model_hint_color'] = body.get('model_hint_color', site['site'].get('model_hint_color', 'rgba(255,255,255,.92)'))
    try:
        site['site']['model_hint_font_size'] = max(10, min(24, int(body.get('model_hint_font_size', site['site'].get('model_hint_font_size', 12)))))
    except Exception:
        site['site']['model_hint_font_size'] = site['site'].get('model_hint_font_size', 12)
    try:
        site['site']['model_hint_max_width'] = max(320, min(1400, int(body.get('model_hint_max_width', site['site'].get('model_hint_max_width', 900)))))
    except Exception:
        site['site']['model_hint_max_width'] = site['site'].get('model_hint_max_width', 900)
    try:
        site['site']['model_hint_radius'] = max(0, min(40, int(body.get('model_hint_radius', site['site'].get('model_hint_radius', 10)))))
    except Exception:
        site['site']['model_hint_radius'] = site['site'].get('model_hint_radius', 10)
    site['theme'] = body.get('theme', site.get('theme', 'warm'))
    if 'thumb_scale' in body:
        site['thumb_scale'] = max(10, min(100, int(body.get('thumb_scale', 50))))
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/favicon', methods=['POST'])
@login_required
def admin_site_favicon():
    site = load_site()
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'favicon_')
    if 'site' not in site: site['site'] = {}
    site['site']['favicon'] = filename
    save_site(site)
    return jsonify({'success': True, 'favicon': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/favicon-from-media', methods=['POST'])
@login_required
def admin_favicon_from_media():
    body = request.json or {}
    filename = body.get('filename', '')
    if not filename:
        return jsonify({'success': False, 'error': '无效文件名'}), 400
    site = load_site()
    if 'site' not in site: site['site'] = {}
    site['site']['favicon'] = filename
    save_site(site)
    return jsonify({'success': True, 'favicon': filename})

@app.route('/admin/site/hero', methods=['PUT'])
@login_required
def admin_hero():
    site = load_site()
    body = request.json
    site['hero']['height'] = int(body.get('height', site['hero']['height']))
    site['hero']['enabled'] = body.get('enabled', site['hero'].get('enabled', True))
    site['hero']['slides'] = body.get('slides', site['hero']['slides'])
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/hero/upload-bg', methods=['POST'])
@login_required
def admin_hero_upload_bg():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file, 'hero_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/nav', methods=['PUT'])
@login_required
def admin_nav():
    site = load_site()
    body = request.json
    site['nav']['logo'] = body.get('logo', site['nav']['logo'])
    site['nav']['links'] = body.get('links', site['nav']['links'])
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/footer', methods=['PUT'])
@login_required
def admin_footer():
    site = load_site()
    ft = request.json or {}
    for c in ft.get('columns', []) or []:
        c.setdefault('image', '')
    site['footer'] = ft
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/footer/upload-image', methods=['POST'])
@login_required
def admin_footer_upload_image():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename):
        return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'footer_col_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/about', methods=['PUT'])
@login_required
def admin_about():
    site = load_site()
    ab = request.json or {}
    socials = ab.get('socials', []) or []
    for s in socials:
        s.setdefault('hover_image', '')
        s['hover_w'] = max(80, min(800, int(s.get('hover_w', 220) or 220)))
        s['hover_h'] = max(60, min(800, int(s.get('hover_h', 140) or 140)))
    site['about'] = ab
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/about/upload-image', methods=['POST'])
@login_required
def admin_about_upload_image():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'about_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/messages-page/avatar-pool', methods=['PUT'])
@login_required
def admin_avatar_pool_save():
    body = request.json or {}
    site = load_site()
    mp = site.setdefault('messages_page', {})
    mp['avatarPool'] = body.get('avatarPool', [])
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/messages-page/avatar-pool/upload', methods=['POST'])
@login_required
def admin_avatar_pool_upload():
    site = load_site()
    mp = site.setdefault('messages_page', {})
    pool = list(mp.get('avatarPool', []))
    added = []
    for f in request.files.getlist('files'):
        if f and allowed_img(f.filename) and len(pool) < 10:
            fn = save_upload(f, 'pool_avatar_')
            pool.append(fn)
            added.append(fn)
    mp['avatarPool'] = pool
    save_site(site)
    return jsonify({'success': True, 'added': added, 'pool': pool})


@app.route('/admin/site/messages-page', methods=['PUT'])
@login_required
def admin_messages_page():
    site = load_site()
    site['messages_page'] = request.json
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/messages-page/upload-bg', methods=['POST'])
@login_required
def admin_messages_page_bg():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file, 'msgbg_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

# ── 媒体库 API ──
@app.route('/admin/media')
@login_required
def admin_media_list():
    """列出所有上传文件，附带引用信息"""
    import os, re
    upload_dir = app.config['UPLOAD_FOLDER']
    data = load_data()
    site = load_site()
    messages = load_messages()

    # 收集所有被引用的文件名
    refs = {}  # filename -> list of ref descriptions

    # 内容引用
    for item in data['items']:
        for field in ['filename', 'cover']:
            fn = item.get(field)
            if fn:
                refs.setdefault(fn, [])
                label = '作品：' + (item.get('title') or '(无标题)') + (' [封面]' if field == 'cover' else ' [主文件]')
                refs[fn].append(label)

    # 站点引用（hero, about, messages_page, favicon）
    def scan_site_refs(obj, path=''):
        if isinstance(obj, dict):
            for k, v in obj.items():
                scan_site_refs(v, path + '.' + k if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                scan_site_refs(v, path + f'[{i}]')
        elif isinstance(obj, str) and obj and not obj.startswith(('http','linear','radial','#','data:')):
            # Likely a filename if it has an extension
            if '.' in obj and len(obj) < 200:
                refs.setdefault(obj, [])
                refs[obj].append('站点配置：' + path)
    scan_site_refs(site)

    # 获取文件列表
    files = []
    if os.path.exists(upload_dir):
        for fn in os.listdir(upload_dir):
            fp = os.path.join(upload_dir, fn)
            if os.path.isfile(fp):
                stat = os.stat(fp)
                ext = fn.rsplit('.', 1)[-1].lower() if '.' in fn else ''
                ftype = 'model' if ext in {'glb','gltf'} else ('video' if ext in {'mp4','mov','webm'} else ('image' if ext in {'png','jpg','jpeg','gif','webp'} else 'other'))
                files.append({
                    'filename': fn,
                    'size': stat.st_size,
                    'type': ftype,
                    'ext': ext,
                    'refs': refs.get(fn, []),
                    'url': '/static/uploads/' + fn,
                    'cover': None,  # filled below
                })
    # 为每个视频文件找封面图（从 content.json 和 showcase.json）
    video_covers = {}
    for item in data['items']:
        if item.get('type') == 'video' and item.get('cover') and item.get('filename'):
            video_covers[item['filename']] = item['cover']
    # featured 引用
    try:
        ft_data = load_featured()
        for item in ft_data.get('items', []):
            for fn in item.get('images', []):
                if fn and not fn.startswith('http'):
                    refs.setdefault(fn, [])
                    refs[fn].append('详情精选：' + (item.get('title') or '(无标题)'))
    except Exception:
        pass
    try:
        sc_data = load_showcase()
        for item in sc_data.get('items', []):
            if item.get('type') == 'video' and item.get('cover') and item.get('filename'):
                video_covers[item['filename']] = item['cover']
    except Exception:
        pass
    for f in files:
        if f['type'] == 'video' and f['filename'] in video_covers:
            f['cover'] = video_covers[f['filename']]
    files.sort(key=lambda f: -os.path.getmtime(os.path.join(upload_dir, f['filename'])))
    return jsonify({'files': files, 'total': len(files)})

@app.route('/admin/media/delete/<filename>', methods=['DELETE'])
@login_required
def admin_media_delete(filename):
    """删除媒体文件（同步清理内容数据里的引用）"""
    import os
    # Security: only allow plain filenames
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'success': False, 'error': '非法文件名'}), 400
    fp = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(fp):
        os.remove(fp)
    # Clean references in content
    data = load_data()
    changed = False
    for item in data['items']:
        if item.get('filename') == filename:
            item['filename'] = ''
            changed = True
        if item.get('cover') == filename:
            item['cover'] = None
            changed = True
    if changed:
        save_data(data)
    return jsonify({'success': True})

@app.route('/admin/media/replace/<filename>', methods=['POST'])
@login_required
def admin_media_replace(filename):
    """替换媒体文件（保持同名，更新内容引用）"""
    import os
    if '/' in filename or '\\' in filename or '..' in filename:
        return jsonify({'success': False, 'error': '非法文件名'}), 400
    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '无效文件'}), 400
    # Save as new file
    new_filename = save_upload(file)
    # Update all references in content
    data = load_data()
    changed = False
    for item in data['items']:
        if item.get('filename') == filename:
            item['filename'] = new_filename
            item['type'] = 'model' if is_model(new_filename) else ('video' if is_video(new_filename) else 'image')
            changed = True
        if item.get('cover') == filename:
            item['cover'] = new_filename
            changed = True
    if changed:
        save_data(data)
    # Delete old file
    old_fp = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(old_fp):
        os.remove(old_fp)
    return jsonify({'success': True, 'new_filename': new_filename, 'url': '/static/uploads/' + new_filename})

# ════════════════════════════════════════

EMOJI_FILE = os.path.join(_BASE, 'data', 'emoji.json')
MUYU_FILE  = os.path.join(_BASE, 'data', 'muyu.json')

def load_muyu():
    import json as _json
    default = {
        'messages': [
            {'text': '功德+1，佛祖保佑你', 'color': '#f5e6c8', 'size': 28, 'style': 'float'},
            {'text': '心想事成，万事如意', 'color': '#ffd700', 'size': 24, 'style': 'burst'},
            {'text': '健康平安，诸事顺遂', 'color': '#98ffb0', 'size': 26, 'style': 'spin'},
            {'text': '财源广进，福气满满', 'color': '#ffaa55', 'size': 25, 'style': 'zoom'}
        ],
        'vip': {'name': 'VIP自动敲', 'speed': 1000, 'enabled': True},
        'svip': {'name': 'SVIP自动狂敲', 'speed': 180, 'enabled': True},
        'title': '电子木鱼',
        'subtitle': '敲电子木鱼，见机甲佛祖，修赛博真经',
        'total_label': '功德',
        'bg_color': '#0a0a08',
        'sound_enabled': True,
        'custom_sound': '',
        'custom_svg': '',
        'custom_image': '',
        # 多木鱼图案（图片为主），供前端用户切换
        # item: {id, name, file}
        'patterns': [],
        'pattern_btn_label': '敲咪咪',
        'pattern_btn_icon': '🧩',
        'back_label': '返回首页',
        'sound_code': '',
        'bg_music_list': [],
        'bg_music_btn_label': '背景音乐',
        'bg_music_stop_label': '停止播放',
        # 背景图层：最多 3 层，每层 PNG，可设置透明度、缩放波动、跟随敲击、旋转及速度
        # opacity, scale, follow_hit, hit_scale, rotate: bool, rotate_speed: 秒/圈
        'bg_layers': []
    }
    d = load_json(MUYU_FILE, default)
    # 补全缺失字段
    for k, v in default.items():
        if k not in d:
            d[k] = v
    # 兼容：旧版只设置了 custom_image，但未建立 patterns
    if d.get('custom_image') and not d.get('patterns'):
        d['patterns'] = [{
            'id': 'legacy_custom_image',
            'name': '自定义图案',
            'file': d.get('custom_image')
        }]
    if 'pattern_btn_label' not in d:
        d['pattern_btn_label'] = default.get('pattern_btn_label', '敲咪咪')
    if 'pattern_btn_icon' not in d:
        d['pattern_btn_icon'] = default.get('pattern_btn_icon', '🧩')
    return d

def save_muyu(d): save_json(MUYU_FILE, d)

def load_emoji():
    return load_json(EMOJI_FILE, {"items": []})

def save_emoji(d): save_json(EMOJI_FILE, d)

FEATURED_FILE = os.path.join(_BASE, 'data', 'featured.json')

def load_featured():
    d = load_json(FEATURED_FILE, {"items": [], "config": {}})
    if "config" not in d: d["config"] = {}
    cfg = d["config"]
    cfg.setdefault("enabled", False)
    cfg.setdefault("title", "详情精选")
    cfg.setdefault("subtitle", "FEATURED")
    cfg.setdefault("position", "after_showcase")
    for it in d.get('items', []) or []:
        it.setdefault('content', '')
    return d

def save_featured(d): save_json(FEATURED_FILE, d)

# ══════════════════════════════════════════
# 电子木鱼路由
# ══════════════════════════════════════════

@app.route('/muyu')
def muyu_page():
    record_visitor()
    return render_template('muyu.html')

@app.route('/api/muyu')
def api_muyu():
    return jsonify(load_muyu())

@app.route('/admin/muyu/upload-sound', methods=['POST'])
@login_required
def admin_muyu_upload_sound():
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': '无文件'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ('mp3', 'wav', 'ogg', 'm4a', 'aac'):
        return jsonify({'success': False, 'error': '仅支持 mp3/wav/ogg/m4a/aac'}), 400
    fn = save_upload(f, 'muyu_sound_')
    d = load_muyu()
    d['custom_sound'] = fn
    save_muyu(d)
    return jsonify({'success': True, 'filename': fn, 'url': '/static/uploads/' + fn})

@app.route('/admin/muyu/upload-svg', methods=['POST'])
@login_required
def admin_muyu_upload_svg():
    """接收 SVG 文本内容保存"""
    body = request.json or {}
    svg_content = body.get('svg', '').strip()
    if not svg_content or '<svg' not in svg_content:
        return jsonify({'success': False, 'error': '无效 SVG'}), 400
    # 存到 data/muyu_custom.svg（不放 uploads，避免被清理）
    svg_path = os.path.join(_BASE, 'data', 'muyu_custom.svg')
    with open(svg_path, 'w', encoding='utf-8') as fp:
        fp.write(svg_content)
    d = load_muyu()
    d['custom_svg'] = 'data/muyu_custom.svg'
    # SVG 与自定义图片互斥：保存 SVG 时清除图片
    d['custom_image'] = ''
    save_muyu(d)
    return jsonify({'success': True})

@app.route('/admin/muyu/svg-content')
@login_required
def admin_muyu_svg_content():
    svg_path = os.path.join(_BASE, 'data', 'muyu_custom.svg')
    if os.path.exists(svg_path):
        with open(svg_path, 'r', encoding='utf-8') as fp:
            return fp.read(), 200, {'Content-Type': 'image/svg+xml'}
    return '', 404


@app.route('/api/muyu/svg-content')
def api_muyu_svg_content():
    """公开读取木鱼 SVG（前台页面使用，避免未登录访问 admin 路由）"""
    svg_path = os.path.join(_BASE, 'data', 'muyu_custom.svg')
    if os.path.exists(svg_path):
        with open(svg_path, 'r', encoding='utf-8') as fp:
            return fp.read(), 200, {'Content-Type': 'image/svg+xml'}
    return '', 404


@app.route('/admin/muyu/upload-image', methods=['POST'])
@login_required
def admin_muyu_upload_image():
    """上传木鱼图像（图片文件），保存到 uploads 并写入 muyu 配置"""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': '无文件'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
        return jsonify({'success': False, 'error': '仅支持 png/jpg/webp/gif'}), 400
    fn = save_upload(f, 'muyu_img_')
    d = load_muyu()
    d['custom_image'] = fn
    # 自定义图片与 SVG 互斥：保存图片时清除 SVG
    d['custom_svg'] = ''
    save_muyu(d)
    return jsonify({'success': True, 'filename': fn, 'url': '/static/uploads/' + fn})


@app.route('/admin/muyu/patterns/upload', methods=['POST'])
@login_required
def admin_muyu_patterns_upload():
    """上传木鱼图案（图片），追加到 patterns"""
    f = request.files.get('file')
    name = (request.form.get('name') or '').strip()
    if not f or not f.filename:
        return jsonify({'success': False, 'error': '无文件'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ('png', 'jpg', 'jpeg', 'webp', 'gif'):
        return jsonify({'success': False, 'error': '仅支持 png/jpg/webp/gif'}), 400
    fn = save_upload(f, 'muyu_pat_')
    d = load_muyu()
    d.setdefault('patterns', [])
    item = {'id': str(uuid.uuid4()), 'name': name or os.path.basename(f.filename), 'file': fn}
    d['patterns'].append(item)
    save_muyu(d)
    return jsonify({'success': True, 'item': item, 'patterns': d['patterns'], 'url': '/static/uploads/' + fn})


@app.route('/admin/muyu/patterns/add-from-media', methods=['POST'])
@login_required
def admin_muyu_patterns_add_from_media():
    body = request.json or {}
    fn = (body.get('filename') or '').strip()
    name = (body.get('name') or '').strip()
    if not fn:
        return jsonify({'success': False, 'error': '无文件名'}), 400
    d = load_muyu()
    d.setdefault('patterns', [])
    item = {'id': str(uuid.uuid4()), 'name': name or os.path.basename(fn), 'file': fn}
    d['patterns'].append(item)
    save_muyu(d)
    return jsonify({'success': True, 'item': item, 'patterns': d['patterns']})


@app.route('/admin/muyu/patterns/add-from-url', methods=['POST'])
@login_required
def admin_muyu_patterns_add_from_url():
    """从 URL 下载图片并追加到 patterns（保存到 uploads）"""
    body = request.json or {}
    url = (body.get('url') or '').strip()
    name = (body.get('name') or '').strip()
    if not url or not url.startswith('http'):
        return jsonify({'success': False, 'error': '无效URL'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get('Content-Type', '')
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or ''
            url_path = urllib.parse.urlparse(url).path
            url_ext = os.path.splitext(url_path)[1].lower()
            if url_ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                ext = url_ext
            elif ext in ('.jpeg',):
                ext = '.jpg'
            elif ext not in ('.jpg', '.png', '.gif', '.webp'):
                ext = '.png'
            data = resp.read(25 * 1024 * 1024)  # 最大 25MB
        fn = 'muyu_pat_url_' + str(uuid.uuid4())[:8] + ext
        path = os.path.join(UPLOAD_FOLDER, fn)
        with open(path, 'wb') as f:
            f.write(data)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    d = load_muyu()
    d.setdefault('patterns', [])
    item = {'id': str(uuid.uuid4()), 'name': name or os.path.basename(fn), 'file': fn}
    d['patterns'].append(item)
    save_muyu(d)
    return jsonify({'success': True, 'item': item, 'patterns': d['patterns'], 'url': '/static/uploads/' + fn})


@app.route('/admin/muyu/patterns/<pid>', methods=['DELETE'])
@login_required
def admin_muyu_patterns_delete(pid):
    d = load_muyu()
    items = d.get('patterns', [])
    d['patterns'] = [i for i in items if i.get('id') != pid]
    save_muyu(d)
    return jsonify({'success': True, 'patterns': d['patterns']})


@app.route('/admin/muyu', methods=['PUT'])
@login_required
def admin_muyu_save():
    body = request.json or {}
    d = load_muyu()
    allowed = [
        'messages', 'vip', 'svip', 'title', 'subtitle', 'total_label', 'sound_enabled',
        'back_label', 'sound_code', 'custom_sound', 'custom_svg', 'custom_image',
        'bg_music_list', 'bg_music_btn_label', 'bg_music_stop_label',
        'bg_color',
        'bg_layers',
        'patterns',
        'pattern_btn_label',
        'pattern_btn_icon'
    ]
    for k in allowed:
        if k in body:
            d[k] = body[k]

    # custom_image 与 custom_svg 互斥：仅允许一个生效
    if ('custom_image' in body) and body.get('custom_image'):
        d['custom_svg'] = ''
    if ('custom_svg' in body) and body.get('custom_svg'):
        d['custom_image'] = ''

    save_muyu(d)
    return jsonify({'success': True})


@app.route('/admin/muyu/upload-bg', methods=['POST'])
@login_required
def admin_muyu_upload_bg():
    """上传电子木鱼背景图片（建议 PNG），存入 uploads，返回文件名和 URL"""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'success': False, 'error': '无文件'}), 400
    ext = f.filename.rsplit('.', 1)[-1].lower() if '.' in f.filename else ''
    if ext not in ('png', 'jpg', 'jpeg', 'webp'):
        return jsonify({'success': False, 'error': '仅支持 PNG/JPG/WebP 图片'}), 400
    fn = save_upload(f, 'muyu_bg_')
    # 配置中的 bg_layers 由前端统一写入，这里只负责保存文件
    return jsonify({'success': True, 'filename': fn, 'url': '/static/uploads/' + fn})


# ── 表情包路由 ──

@app.route('/api/emoji')
def api_emoji():
    return jsonify(load_emoji())

@app.route('/admin/emoji/upload', methods=['POST'])
@login_required
def admin_emoji_upload():
    d = load_emoji()
    for f in request.files.getlist('files'):
        if f and allowed_img(f.filename):
            fn = save_upload(f, 'emoji_')
            tag = request.form.get('tag', '').strip()
            d['items'].append({'id': str(uuid.uuid4()), 'filename': fn, 'tag': tag})
    save_emoji(d)
    return jsonify({'success': True, 'items': d['items']})

@app.route('/admin/emoji/<eid>', methods=['DELETE'])
@login_required
def admin_emoji_delete(eid):
    d = load_emoji()
    d['items'] = [i for i in d['items'] if i['id'] != eid]
    save_emoji(d)
    return jsonify({'success': True})

@app.route('/admin/emoji/add-from-media', methods=['POST'])
@login_required
def admin_emoji_add_from_media():
    body = request.json or {}
    fn = body.get('filename', '').strip()
    tag = body.get('tag', '').strip()
    if not fn:
        return jsonify({'success': False, 'error': '无文件名'}), 400
    data = load_emoji()
    item = {'id': str(uuid.uuid4()), 'filename': fn, 'tag': tag}
    data['items'].append(item)
    save_emoji(data)
    return jsonify({'success': True, 'items': data['items']})

@app.route('/admin/emoji/add-from-url', methods=['POST'])
@login_required
def admin_emoji_add_from_url():
    import urllib.request as _ur
    body = request.json or {}
    url = body.get('url', '').strip()
    tag = body.get('tag', '').strip()
    if not url or not url.startswith('http'):
        return jsonify({'success': False, 'error': '无效URL'}), 400
    # 下载图片并保存
    ext = url.split('?')[0].rsplit('.', 1)[-1].lower() if '.' in url.split('?')[0] else 'png'
    if ext not in ('png', 'gif', 'webp', 'jpg', 'jpeg'):
        ext = 'png'
    fn = 'emoji_url_' + str(uuid.uuid4())[:8] + '.' + ext
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], fn)
    try:
        req = _ur.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with _ur.urlopen(req, timeout=8) as resp, open(save_path, 'wb') as fp:
            fp.write(resp.read())
    except Exception as e:
        return jsonify({'success': False, 'error': f'下载失败: {str(e)}'}), 400
    data = load_emoji()
    item = {'id': str(uuid.uuid4()), 'filename': fn, 'tag': tag}
    data['items'].append(item)
    save_emoji(data)
    return jsonify({'success': True, 'items': data['items']})


@app.route('/admin/emoji/reorder', methods=['POST'])
@login_required
def admin_emoji_reorder():
    ids = (request.json or {}).get('ids', [])
    d = load_emoji()
    lk = {i['id']: i for i in d['items']}
    d['items'] = [lk[i] for i in ids if i in lk]
    save_emoji(d)
    return jsonify({'success': True})


# ── 详情精选 路由 ──

@app.route('/api/featured')
def api_featured():
    data = load_featured()
    return jsonify({"items": data["items"], "config": data["config"]})

# ── 数据备份 / 恢复 ──

DATA_TYPES = {
    'content':   DATA_FILE,
    'site':      SITE_FILE,
    'messages':  MESSAGES_FILE,
    'visitors':  VISITORS_FILE,
    'likes':     LIKES_FILE,
    'auth':      AUTH_FILE,
    'smtp':      SMTP_FILE,
    'featured':  FEATURED_FILE,
    'emoji':     EMOJI_FILE,
    'muyu':      MUYU_FILE,
    'showcase':  SHOWCASE_FILE if 'SHOWCASE_FILE' in globals() else 'data/showcase.json',
}


def _all_data_json_files():
    """返回 data 目录下所有 JSON 文件（自动纳入备份）"""
    data_dir = os.path.join(_BASE, 'data')
    files = []
    if os.path.isdir(data_dir):
        for fn in os.listdir(data_dir):
            if fn.lower().endswith('.json'):
                files.append(os.path.join(data_dir, fn))
    return sorted(files)

@app.route('/admin/backup/export', methods=['POST'])
@login_required
def admin_backup_export():
    """打包动态数据（默认 data/*.json 全量）及媒体文件为 zip 下载"""
    body = request.json or {}
    req_types = body.get('types', list(DATA_TYPES.keys()))
    include_uploads = body.get('include_uploads', True)
    include_thumbs  = body.get('include_thumbs', True)

    # 动态数据：默认全量 data/*.json；如前端传了 types，则在全量基础上保持兼容
    export_files = {os.path.abspath(p) for p in _all_data_json_files()}
    for t in req_types:
        fp = DATA_TYPES.get(t)
        if fp:
            export_files.add(os.path.abspath(fp))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fp in sorted(export_files):
            if os.path.exists(fp):
                zf.write(fp, f'data/{os.path.basename(fp)}')
        # 附加：木鱼自定义 SVG 文件（不在 JSON 内）+ 木鱼引用的媒体文件
        if 'muyu' in req_types:
            svg_path = os.path.join(_BASE, 'data', 'muyu_custom.svg')
            if os.path.exists(svg_path):
                zf.write(svg_path, 'data/muyu_custom.svg')

            # 无论是否勾选“媒体文件”，都把木鱼配置里引用到的 uploads 文件打包，避免迁移丢失
            try:
                mcfg = load_muyu() or {}
                refs = set()

                def _add_ref(v):
                    if not isinstance(v, str):
                        return
                    s = v.strip()
                    if not s:
                        return
                    if s.startswith('http://') or s.startswith('https://'):
                        return
                    refs.add(os.path.basename(s))

                _add_ref(mcfg.get('custom_sound'))
                _add_ref(mcfg.get('custom_image'))
                for p in (mcfg.get('patterns') or []):
                    _add_ref((p or {}).get('file'))
                for bl in (mcfg.get('bg_layers') or []):
                    _add_ref((bl or {}).get('file'))

                for fn in refs:
                    fp = os.path.join(UPLOAD_FOLDER, fn)
                    if os.path.isfile(fp):
                        zf.write(fp, f'muyu_uploads/{fn}')
            except Exception:
                pass
        if include_uploads and os.path.isdir(UPLOAD_FOLDER):
            for fn in os.listdir(UPLOAD_FOLDER):
                fp = os.path.join(UPLOAD_FOLDER, fn)
                if os.path.isfile(fp):
                    zf.write(fp, f'uploads/{fn}')
        if include_thumbs and os.path.isdir(THUMBS_FOLDER):
            for fn in os.listdir(THUMBS_FOLDER):
                fp = os.path.join(THUMBS_FOLDER, fn)
                if os.path.isfile(fp):
                    zf.write(fp, f'thumbs/{fn}')
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='gallery_backup.zip')

@app.route('/admin/backup/import', methods=['POST'])
@login_required
def admin_backup_import():
    """从 zip 文件恢复数据（默认恢复 zip 内全部 data/*.json）"""
    f = request.files.get('file')
    if not f:
        return jsonify({'success': False, 'error': '缺少文件'}), 400
    types   = request.form.getlist('types')
    uploads = request.form.get('include_uploads') == '1'
    thumbs  = request.form.get('include_thumbs')  == '1'
    restored = []
    try:
        with zipfile.ZipFile(f.stream, 'r') as zf:
            names = zf.namelist()
            # 默认：恢复压缩包内所有 data/*.json
            for nm in names:
                if nm.startswith('data/') and nm.lower().endswith('.json') and not nm.endswith('/'):
                    base = os.path.basename(nm)
                    dst = os.path.join(_BASE, 'data', base)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(nm) as src:
                        with open(dst, 'wb') as out:
                            out.write(src.read())
                    restored.append(base)

            # 兼容旧逻辑：若传了 types 且 zip 中存在，确保对应文件被恢复
            for t in types:
                fp = DATA_TYPES.get(t)
                arc = f'data/{os.path.basename(fp)}' if fp else None
                if arc and arc in names and fp:
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    with zf.open(arc) as src:
                        with open(fp, 'wb') as dst:
                            dst.write(src.read())
                    if t not in restored:
                        restored.append(t)

            # 附加：木鱼自定义 SVG + 木鱼专属媒体
            if ('muyu' in types) or ('data/muyu.json' in names):
                if 'data/muyu_custom.svg' in names:
                    svg_path = os.path.join(_BASE, 'data', 'muyu_custom.svg')
                    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
                    with zf.open('data/muyu_custom.svg') as src:
                        with open(svg_path, 'wb') as dst:
                            dst.write(src.read())
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                for nm in names:
                    if nm.startswith('muyu_uploads/') and not nm.endswith('/'):
                        fn = os.path.basename(nm)
                        with zf.open(nm) as src:
                            with open(os.path.join(UPLOAD_FOLDER, fn), 'wb') as dst:
                                dst.write(src.read())

            if uploads:
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                for nm in names:
                    if nm.startswith('uploads/') and not nm.endswith('/'):
                        fn = os.path.basename(nm)
                        with zf.open(nm) as src:
                            with open(os.path.join(UPLOAD_FOLDER, fn), 'wb') as dst:
                                dst.write(src.read())
                restored.append('uploads')
            if thumbs:
                os.makedirs(THUMBS_FOLDER, exist_ok=True)
                for nm in names:
                    if nm.startswith('thumbs/') and not nm.endswith('/'):
                        fn = os.path.basename(nm)
                        with zf.open(nm) as src:
                            with open(os.path.join(THUMBS_FOLDER, fn), 'wb') as dst:
                                dst.write(src.read())
                restored.append('thumbs')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    return jsonify({'success': True, 'restored': restored})


@app.route('/admin/featured')
@login_required
def admin_featured_list():
    return jsonify(load_featured())

@app.route('/admin/featured/config', methods=['PUT'])
@login_required
def admin_featured_config():
    body = request.json or {}
    data = load_featured()
    cfg = data['config']
    cfg['enabled']  = bool(body.get('enabled', cfg.get('enabled', False)))
    cfg['title']    = body.get('title', cfg.get('title', '详情精选'))
    cfg['subtitle'] = body.get('subtitle', cfg.get('subtitle', 'FEATURED'))
    cfg['position'] = body.get('position', cfg.get('position', 'after_showcase'))
    save_featured(data)
    return jsonify({'success': True, 'config': cfg})

@app.route('/admin/featured/reorder', methods=['POST'])
@login_required
def admin_featured_reorder():
    ids = (request.json or {}).get('ids', [])
    data = load_featured()
    lookup = {i['id']: i for i in data['items']}
    data['items'] = [lookup[i] for i in ids if i in lookup]
    save_featured(data)
    return jsonify({'success': True})

@app.route('/admin/featured/upload', methods=['POST'])
@login_required
def admin_featured_upload():
    data = load_featured()
    images = []
    for f in request.files.getlist('images'):
        if f and f.filename and allowed_img(f.filename):
            images.append(save_upload(f))
    for fn in request.form.getlist('existing_images'):
        if fn: images.append(fn)
    if not images:
        return jsonify({'success': False, 'error': '至少需要一张图片'}), 400
    cover = request.form.get('cover', '').strip()
    item = {
        'id': str(uuid.uuid4()),
        'title': request.form.get('title', '').strip(),
        'content': request.form.get('content', '').strip(),
        'images': images,
        'cover': cover,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    data['items'].insert(0, item)
    save_featured(data)
    return jsonify({'success': True, 'item': item})

@app.route('/admin/featured/<item_id>', methods=['PUT'])
@login_required
def admin_featured_update(item_id):
    data = load_featured()
    item = next((i for i in data['items'] if i['id'] == item_id), None)
    if not item:
        return jsonify({'success': False, 'error': '未找到'}), 404
    if request.is_json:
        body = request.json or {}
        if 'title' in body: item['title'] = body['title']
        if 'content' in body: item['content'] = body['content']
        if 'images_order' in body: item['images'] = body['images_order']
        if 'cover' in body: item['cover'] = body['cover']
    else:
        for f in request.files.getlist('images'):
            if f and f.filename and allowed_img(f.filename):
                item.setdefault('images', []).append(save_upload(f))
        for fn in request.form.getlist('existing_images'):
            if fn: item.setdefault('images', []).append(fn)
        order = request.form.getlist('images_order')
        if order: item['images'] = order
    save_featured(data)
    return jsonify({'success': True, 'item': item})

@app.route('/admin/featured/<item_id>', methods=['DELETE'])
@login_required
def admin_featured_delete(item_id):
    data = load_featured()
    data['items'] = [i for i in data['items'] if i['id'] != item_id]
    save_featured(data)
    return jsonify({'success': True})

SHOWCASE_FILE = 'data/showcase.json'

def load_showcase():
    d = load_json(SHOWCASE_FILE, {"items": [], "config": {}})
    if "config" not in d:
        d["config"] = {}
    cfg = d["config"]
    cfg.setdefault("enabled", True)
    cfg.setdefault("title", "橱窗精选")
    cfg.setdefault("subtitle", "SHOWCASE")
    cfg.setdefault("columns", 4)
    cfg.setdefault("cardHeight", 200)
    return d

def save_showcase(d):
    save_json(SHOWCASE_FILE, d)

@app.route('/api/showcase')
def api_showcase():
    """公开接口：返回橱窗内容（含点赞数）+ config"""
    data = load_showcase()
    likes = load_likes()
    items = [dict(i) for i in data['items']]
    for item in items:
        item['likes'] = likes.get('sc_' + item['id'], 0)
    return jsonify({"items": items, "config": data["config"]})

@app.route('/api/showcase/like/<item_id>', methods=['POST'])
def api_showcase_like(item_id):
    ip = request.remote_addr or 'unknown'
    likes = load_likes()
    sc_id = 'sc_' + item_id
    ip_key = _ip_key(ip, sc_id)
    currently = likes.get(ip_key, False)
    is_liked = not currently
    likes[ip_key] = is_liked
    likes[sc_id] = max(0, likes.get(sc_id, 0) + (1 if is_liked else -1))
    save_likes(likes)
    return jsonify({'success': True, 'liked': is_liked, 'likes': likes[sc_id]})

@app.route('/admin/showcase')
@login_required
def admin_showcase_list():
    data = load_showcase()
    likes = load_likes()
    items = [dict(i) for i in data['items']]
    for item in items:
        item['likes'] = likes.get('sc_' + item['id'], 0)
    return jsonify({"items": items, "config": data["config"]})

@app.route('/admin/showcase/config', methods=['PUT'])
@login_required
def admin_showcase_config():
    data = load_showcase()
    body = request.json or {}
    cfg = data["config"]
    cfg["enabled"] = bool(body.get("enabled", True))
    cfg["title"] = body.get("title", "橱窗精选")
    cfg["subtitle"] = body.get("subtitle", "SHOWCASE")
    cfg["columns"] = int(body.get("columns", 4))
    cfg["cardHeight"] = max(100, min(800, int(body.get("cardHeight", 200))))
    cfg["cardWidth"] = max(120, min(600, int(body.get("cardWidth", 280))))
    cfg["scrollSpeed"] = max(0, min(300, int(body.get("scrollSpeed", 0))))
    save_showcase(data)
    return jsonify({"success": True})

@app.route('/admin/showcase/upload', methods=['POST'])
@login_required
def admin_showcase_upload():
    data = load_showcase()
    file = request.files.get('file')
    cover = request.files.get('cover')
    existing_file = request.form.get('existing_file', '')
    existing_cover = request.form.get('existing_cover', '')
    if not file and not existing_file:
        return jsonify({'success': False, 'error': '无效文件'}), 400
    if file:
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': '无效文件'}), 400
        filename = save_upload(file)
    else:
        filename = existing_file
    cover_filename = None
    if cover and allowed_img(cover.filename):
        cover_filename = save_upload(cover, 'sc_cover_')
    elif existing_cover:
        cover_filename = existing_cover
    likes = load_likes()
    item_id = str(uuid.uuid4())
    item = {
        'id': item_id,
        'title': request.form.get('title', ''),
        'description': request.form.get('description', ''),
        'link': request.form.get('link', ''),
        'filename': filename,
        'cover': cover_filename,
        'type': 'model' if is_model(filename) else ('video' if is_video(filename) else 'image'),
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'width': int(request.form.get('width', 16)),
        'height': int(request.form.get('height', 9)),
    }
    likes['sc_' + item_id] = 0
    save_likes(likes)
    data['items'].append(item)
    save_showcase(data)
    return jsonify({'success': True, 'item': item})

@app.route('/admin/showcase/<item_id>', methods=['PUT'])
@login_required
def admin_showcase_edit(item_id):
    data = load_showcase()
    body = request.json or {}
    for item in data['items']:
        if item['id'] == item_id:
            item['title'] = body.get('title', item.get('title', ''))
            item['description'] = body.get('description', item.get('description', ''))
            item['link'] = body.get('link', item.get('link', ''))
            if 'likes' in body:
                likes = load_likes()
                likes['sc_' + item_id] = max(0, int(body['likes']))
                save_likes(likes)
            break
    save_showcase(data)
    return jsonify({'success': True})

@app.route('/admin/showcase/<item_id>/replace', methods=['POST'])
@login_required
def admin_showcase_replace(item_id):
    data = load_showcase()
    file = request.files.get('file')
    cover = request.files.get('cover')
    existing_file = request.form.get('existing_file', '')
    existing_cover = request.form.get('existing_cover', '')
    for item in data['items']:
        if item['id'] == item_id:
            if file and allowed_file(file.filename):
                item['filename'] = save_upload(file)
                item['type'] = 'model' if is_model(item['filename']) else ('video' if is_video(item['filename']) else 'image')
            elif existing_file:
                item['filename'] = existing_file
                item['type'] = 'model' if is_model(existing_file) else ('video' if is_video(existing_file) else 'image')
            if cover and allowed_img(cover.filename):
                item['cover'] = save_upload(cover, 'sc_cover_')
            elif existing_cover:
                item['cover'] = existing_cover
            break
    save_showcase(data)
    return jsonify({'success': True})

@app.route('/admin/showcase/reorder', methods=['PUT'])
@login_required
def admin_showcase_reorder():
    data = load_showcase()
    order = request.json.get('order', [])
    id_map = {i['id']: i for i in data['items']}
    data['items'] = [id_map[oid] for oid in order if oid in id_map]
    save_showcase(data)
    return jsonify({'success': True})

@app.route('/admin/showcase/<item_id>', methods=['DELETE'])
@login_required
def admin_showcase_delete(item_id):
    data = load_showcase()
    data['items'] = [i for i in data['items'] if i['id'] != item_id]
    save_showcase(data)
    return jsonify({'success': True})

@app.route('/admin/media/cleanup', methods=['POST'])
@login_required
def admin_media_cleanup():
    """删除 uploads 目录中所有未被引用的文件"""
    import os
    upload_dir = app.config['UPLOAD_FOLDER']
    data = load_data()
    site = load_site()
    showcase = load_showcase()

    # 收集所有已引用的文件名
    refs = set()

    # 内容引用
    for item in data['items']:
        for field in ['filename', 'cover']:
            fn = item.get(field)
            if fn: refs.add(fn)

    # 橱窗引用
    for item in showcase.get('items', []):
        for field in ['filename', 'cover']:
            fn = item.get(field)
            if fn: refs.add(fn)

    # 站点配置引用（递归扫描所有字符串值）
    def collect_refs(obj):
        if isinstance(obj, dict):
            for v in obj.values(): collect_refs(v)
        elif isinstance(obj, list):
            for v in obj: collect_refs(v)
        elif isinstance(obj, str) and obj and '.' in obj and len(obj) < 200:
            if not obj.startswith(('http', 'linear', 'radial', '#', 'data:')):
                refs.add(obj)
    collect_refs(site)

    # 扫描 uploads 目录，删除未引用文件
    deleted, skipped, errors = [], [], []
    if os.path.exists(upload_dir):
        for fn in os.listdir(upload_dir):
            fp = os.path.join(upload_dir, fn)
            if not os.path.isfile(fp):
                continue
            if fn in refs:
                skipped.append(fn)
            else:
                try:
                    os.remove(fp)
                    deleted.append(fn)
                except Exception as e:
                    errors.append({'file': fn, 'error': str(e)})

    return jsonify({
        'success': True,
        'deleted': len(deleted),
        'skipped': len(skipped),
        'errors': errors,
        'deletedFiles': deleted
    })

# ════════════════════════════════════════════
# SMTP 配置
# ════════════════════════════════════════
# 详情精选 (Featured) API & Admin routes
@app.route('/admin/smtp', methods=['GET'])
@login_required
def admin_smtp_get():
    cfg = load_smtp()
    safe = dict(cfg)
    safe['password'] = '••••••' if cfg.get('password') else ''
    return jsonify(safe)

@app.route('/admin/smtp/test', methods=['POST'])
@login_required
def admin_smtp_test():
    body = request.json or {}
    import re as _re
    to = body.get('to', '').strip()
    if not to or not _re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', to):
        return jsonify({'success': False, 'error': '收件人邮箱格式不正确'}), 400
    try:
        cfg = load_smtp()
        # 支持用当前表单中的参数临时测试（不保存）
        if body.get('host'): cfg['host'] = body['host']
        if body.get('port'): cfg['port'] = int(body['port'])
        if body.get('user'): cfg['user'] = body['user']
        if 'use_ssl' in body: cfg['use_ssl'] = bool(body['use_ssl'])
        if body.get('from_name'): cfg['from_name'] = body['from_name']
        tmp_pw = body.get('password', '')
        if tmp_pw and tmp_pw != '••••••':
            cfg['password'] = tmp_pw
        msg = MIMEText('Gallery 管理后台 SMTP 测试邮件，收到即说明配置正确。', 'plain', 'utf-8')
        msg['Subject'] = Header('Gallery SMTP Test', 'utf-8')
        msg['From'] = formataddr((str(Header(cfg.get('from_name','Gallery'), 'utf-8')), cfg['user']))
        msg['To'] = to
        _smtp_send(cfg, msg)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ════════════════════════════════════════
# 详情精选 (Featured) API & Admin routes
@app.route('/admin/reset/send', methods=['POST'])
def admin_reset_send():
    """发送重置验证码到管理员邮箱"""
    body = request.json or {}
    username = body.get('username', '')
    auth = load_auth()
    if username != auth.get('username', ''):
        return jsonify({'success': False, 'error': '用户名不存在'}), 400
    email = auth.get('email', '')
    if not email:
        return jsonify({'success': False, 'error': '未设置找回邮箱，请联系服务器管理员'}), 400
    # 防频刷：60秒内只能发一次
    existing = _reset_codes.get(email, {})
    if existing.get('expires', 0) - time.time() > 540:
        return jsonify({'success': False, 'error': '验证码已发送，请60秒后再试'}), 429
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    _reset_codes[email] = {'code': code, 'expires': time.time() + 600}
    try:
        send_reset_email(email, code)
    except Exception as e:
        return jsonify({'success': False, 'error': f'邮件发送失败：{str(e)}'}), 500
    masked = email[:2] + '***' + email[email.find('@'):]
    return jsonify({'success': True, 'masked': masked})

@app.route('/admin/reset/verify', methods=['POST'])
def admin_reset_verify():
    """校验验证码并重置密码"""
    body = request.json or {}
    username = body.get('username', '')
    code = body.get('code', '').strip()
    new_pw = body.get('new_password', '')
    auth = load_auth()
    if username != auth.get('username', ''):
        return jsonify({'success': False, 'error': '用户名错误'}), 400
    email = auth.get('email', '')
    record = _reset_codes.get(email, {})
    if not record or record.get('code') != code:
        return jsonify({'success': False, 'error': '验证码错误'}), 400
    if time.time() > record.get('expires', 0):
        _reset_codes.pop(email, None)
        return jsonify({'success': False, 'error': '验证码已过期'}), 400
    if len(new_pw) < 6:
        return jsonify({'success': False, 'error': '新密码不能少于6位'}), 400
    auth['password'] = hash_pw(new_pw)
    save_json(AUTH_FILE, auth)
    _reset_codes.pop(email, None)
    return jsonify({'success': True})

@app.route('/admin/account/info')
@login_required
def admin_account_info():
    auth = load_auth()
    return jsonify({
        'username': auth.get('username', 'admin'),
        'avatar': auth.get('avatar', ''),
        'email': auth.get('email', '')
    })

@app.route('/admin/account/avatar-get')
@login_required
def admin_account_avatar_get():
    auth = load_auth()
    return jsonify({'avatar': auth.get('avatar', '')})

@app.route('/admin/account/avatar', methods=['POST'])
@login_required
def admin_account_avatar():
    """上传头像"""
    file = request.files.get('file')
    existing = request.form.get('existing_file', '')
    auth = load_auth()
    if file and allowed_img(file.filename):
        filename = save_upload(file, 'avatar_')
        auth['avatar'] = filename
    elif existing:
        auth['avatar'] = existing
    else:
        return jsonify({'success': False, 'error': '无效文件'}), 400
    save_json(AUTH_FILE, auth)
    url = '/static/uploads/' + auth['avatar']
    return jsonify({'success': True, 'avatar': auth['avatar'], 'url': url})

# 账号安全：获取邮箱
@app.route('/admin/account/email-get')
@login_required
def admin_account_email_get():
    auth = load_auth()
    return jsonify({'email': auth.get('email', '')})

# 账号安全：更新邮箱
@app.route('/admin/account/email', methods=['PUT'])
@login_required
def admin_account_email():
    body = request.json or {}
    auth = load_auth()
    auth['email'] = body.get('email', '')
    save_json(AUTH_FILE, auth)
    return jsonify({'success': True})

def init_app():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(THUMBS_FOLDER, exist_ok=True)
    os.makedirs('data', exist_ok=True)
    if not os.path.exists(DATA_FILE):
        save_data({"categories": ["摄影", "插画", "设计", "视频", "其他"], "items": []})
    if not os.path.exists(SITE_FILE):
        save_site(get_default_site())
    if not os.path.exists(FEATURED_FILE):
        save_featured({"items": [], "config": {}})
    if not os.path.exists(EMOJI_FILE):
        save_emoji({"items": []})
    if not os.path.exists(MUYU_FILE):
        save_muyu(load_muyu())
    if not os.path.exists(AUTH_FILE):
        save_json(AUTH_FILE, {"username": "admin", "password": hash_pw("admin123")})

# 模块加载时初始化（兼容 gunicorn / Railway）
init_app()

@app.route('/admin/thumbs', methods=['GET'])
@login_required
def admin_thumbs():
    """缩图库列表，含引用状态"""
    page = int(request.args.get('page', 1))
    per = int(request.args.get('per_page', 30))
    # 建立引用表：thumb文件名 -> item title
    data = load_data()
    ref_map = {}
    for item in data['items']:
        t = item.get('thumb')
        if t:
            ref_map[t] = item.get('title') or item.get('filename', '')
    files = sorted([f for f in os.listdir(THUMBS_FOLDER)
                    if f.lower().endswith(('.jpg','.jpeg','.png','.webp'))],
                   key=lambda f: os.path.getmtime(os.path.join(THUMBS_FOLDER, f)),
                   reverse=True)
    total = len(files)
    chunk = files[(page-1)*per : page*per]
    items = []
    for f in chunk:
        p = os.path.join(THUMBS_FOLDER, f)
        items.append({
            'filename': f,
            'size': os.path.getsize(p),
            'mtime': os.path.getmtime(p),
            'referenced': f in ref_map,
            'ref_title': ref_map.get(f, '')
        })
    return jsonify({'items': items, 'total': total, 'page': page,
                    'per_page': per, 'pages': max(1, (total + per - 1) // per),
                    'has_more': page*per < total})

@app.route('/admin/thumbs/regenerate', methods=['POST'])
@login_required
def admin_regenerate_thumbs():
    """批量重新生成所有图片的缩图"""
    data = load_data()
    site = load_site()
    scale = site.get('thumb_scale', 50)
    count = 0
    for item in data['items']:
        if item.get('type') == 'video':
            continue
        src = item.get('cover') or item.get('filename', '')
        if not src:
            continue
        thumb_fn = make_thumb(src, scale)
        if thumb_fn:
            item['thumb'] = thumb_fn
            count += 1
    save_data(data)
    return jsonify({'success': True, 'count': count})

@app.route('/admin/thumbs/check', methods=['GET'])
@login_required
def admin_check_thumbs():
    """检测哪些图片内容缺少缩图或缩图文件不存在"""
    data = load_data()
    missing = []
    for item in data['items']:
        if item.get('type') == 'video':
            continue
        fn = item.get('filename', '')
        cover = item.get('cover', '')
        # 跳过 URL 外链内容（无法生成本地缩图）
        src = cover or fn
        if src.startswith('http://') or src.startswith('https://'):
            continue
        thumb = item.get('thumb')
        if not thumb or not os.path.exists(os.path.join(THUMBS_FOLDER, thumb)):
            missing.append({
                'id': item['id'],
                'title': item.get('title', '(无标题)'),
                'filename': fn,
                'cover': cover,
            })
    return jsonify({'missing': missing, 'count': len(missing)})

@app.route('/admin/thumbs/fill-missing', methods=['POST'])
@login_required
def admin_fill_missing_thumbs():
    """只为缺少缩图的图片生成缩图"""
    data = load_data()
    site = load_site()
    scale = site.get('thumb_scale', 50)
    count = 0
    for item in data['items']:
        if item.get('type') == 'video':
            continue
        thumb = item.get('thumb')
        if thumb and os.path.exists(os.path.join(THUMBS_FOLDER, thumb)):
            continue
        src = item.get('cover') or item.get('filename', '')
        if not src:
            continue
        thumb_fn = make_thumb(src, scale)
        if thumb_fn:
            item['thumb'] = thumb_fn
            count += 1
    save_data(data)
    return jsonify({'success': True, 'count': count})

@app.route('/admin/thumbs/<filename>', methods=['DELETE'])
@login_required
def admin_delete_thumb(filename):
    path = os.path.join(THUMBS_FOLDER, os.path.basename(filename))
    if os.path.exists(path):
        os.remove(path)
    return jsonify({'success': True})

@app.route('/admin/upload-from-url', methods=['POST'])
@login_required
def admin_upload_from_url():
    """从远程 URL 下载媒体文件并保存到 uploads"""
    url = (request.json or {}).get('url', '').strip()
    if not url:
        return jsonify({'success': False, 'error': '缺少 URL'}), 400
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get('Content-Type', '')
            # 判断扩展名
            ext = mimetypes.guess_extension(content_type.split(';')[0].strip()) or ''
            # 从 URL 末尾猜扩展名
            url_path = urllib.parse.urlparse(url).path
            url_ext = os.path.splitext(url_path)[1].lower()
            if url_ext in ('.jpg','.jpeg','.png','.gif','.webp','.mp4','.mov','.webm','.avi','.glb','.gltf'):
                ext = url_ext
            elif ext in ('.jpeg',): ext = '.jpg'
            elif ext not in ('.jpg','.png','.gif','.webp','.mp4','.mov','.webm','.glb','.gltf'):
                ext = '.jpg'  # 默认
            data = resp.read(50 * 1024 * 1024)  # 最大50MB
        fn = 'url_' + str(uuid.uuid4()) + ext
        path = os.path.join(UPLOAD_FOLDER, fn)
        with open(path, 'wb') as f:
            f.write(data)
        file_type = 'model' if ext in ('.glb','.gltf') else ('video' if ext in ('.mp4','.mov','.webm','.avi') else 'image')
        return jsonify({'success': True, 'filename': fn, 'type': file_type,
                        'url': '/static/uploads/' + fn})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)

SHOWCASE_FILE = 'data/showcase.json'

def load_showcase():
    d = load_json(SHOWCASE_FILE, {"items": [], "config": {}})
    if "config" not in d:
        d["config"] = {}
    cfg = d["config"]
    cfg.setdefault("enabled", True)
    cfg.setdefault("title", "橱窗精选")
    cfg.setdefault("subtitle", "SHOWCASE")
    cfg.setdefault("columns", 4)
    cfg.setdefault("cardHeight", 200)
    return d

def save_showcase(d):
    save_json(SHOWCASE_FILE, d)
if __name__ == '__main__':
    app.run(debug=True)
