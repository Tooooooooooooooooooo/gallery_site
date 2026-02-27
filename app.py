from flask import Flask, render_template, request, jsonify, session, redirect
from functools import wraps
import json, os, uuid, hashlib
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'gallery-secret-key-2024-x9z'

# ========== 修改点1：Volume 路径配置 ==========
# 优先使用 Railway Volume 的环境变量，如果没有则使用默认相对路径
VOLUME_PATH = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', None)
if VOLUME_PATH:
    # 如果设置了 Volume，直接使用 Volume 路径
    UPLOAD_FOLDER = VOLUME_PATH
    print(f"✅ 使用 Volume 路径: {UPLOAD_FOLDER}")
else:
    # 没有 Volume 时使用相对路径（本地开发）
    UPLOAD_FOLDER = 'static/uploads'
    print(f"⚠️ 使用本地路径: {UPLOAD_FOLDER}")

# ========== 修改点2：确保所有数据文件路径也是绝对路径 ==========
# 获取应用根目录
APP_ROOT = os.path.dirname(os.path.abspath(__file__))

# 数据文件路径（使用绝对路径）
DATA_DIR = os.path.join(APP_ROOT, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'content.json')
MESSAGES_FILE = os.path.join(DATA_DIR, 'messages.json')
SITE_FILE = os.path.join(DATA_DIR, 'site.json')
VISITORS_FILE = os.path.join(DATA_DIR, 'visitors.json')
LIKES_FILE = os.path.join(DATA_DIR, 'likes.json')
AUTH_FILE = os.path.join(DATA_DIR, 'auth.json')
SHOWCASE_FILE = os.path.join(DATA_DIR, 'showcase.json')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'webm'}
IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

# ========== 修改点3：确保上传目录存在 ==========
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def allowed_file(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def allowed_img(f): return '.' in f and f.rsplit('.', 1)[1].lower() in IMG_EXTENSIONS
def is_video(f): return f.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'webm'}
def hash_pw(pw): return hashlib.sha256(pw.encode()).hexdigest()

def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    # ========== 修改点4：确保目录存在 ==========
    os.makedirs(os.path.dirname(path), exist_ok=True)
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
def load_auth(): return load_json(AUTH_FILE, {"username": "admin", "password": hash_pw("admin123")})

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated

def get_default_site():
    return {
        "site": {"title": "GALLERY · 视觉创作集", "subtitle": "记录生活之美，分享视觉灵感", "favicon": ""},
        "theme": "warm",
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
            "socials": [{"label": "微博", "icon": "", "href": "#"}, {"label": "Instagram", "icon": "", "href": "#"}, {"label": "小红书", "icon": "", "href": "#"}]
        },
        "messages_page": {
            "bgType": "gradient",
            "bgValue": "linear-gradient(135deg, #1a1208 0%, #3d2510 50%, #6b3d18 100%)",
            "title": "留言板",
            "subtitle": "留下你的足迹，与我分享你的想法",
            "defaultAvatar": ""
        },
        "footer": {
            "brand": {"logo": "GAL·LERY", "desc": "记录生活之美，分享视觉灵感。\n每一帧都是独一无二的故事。"},
            "columns": [
                {"title": "导航", "links": [
                    {"label": "作品集", "href": "#gallery"}, {"label": "关于我", "href": "/about"},
                    {"label": "留言板", "href": "/messages"}, {"label": "管理后台", "href": "/admin"}
                ]},
                {"title": "关于", "links": [
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
    if 'about' in d:
        for k, v in default['about'].items():
            if k not in d['about']: d['about'][k] = v
    if 'messages_page' not in d: d['messages_page'] = default['messages_page']
    if 'theme' not in d: d['theme'] = 'warm'
    if 'enabled' not in d.get('hero', {}): d['hero']['enabled'] = True
    return d

def save_site(d): save_json(SITE_FILE, d)

def save_upload(file, prefix=''):
    ext = file.filename.rsplit('.', 1)[1].lower()
    fn = prefix + str(uuid.uuid4()) + '.' + ext
    # ========== 修改点5：使用配置的 UPLOAD_FOLDER ==========
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    return fn

def record_visitor():
    visitors = load_visitors()
    v = {'id': str(uuid.uuid4()), 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
         'ip': request.remote_addr or 'unknown', 'ua': request.headers.get('User-Agent', '')[:200],
         'path': request.path, 'referer': request.referrer or ''}
    visitors.insert(0, v)
    if len(visitors) > 2000: visitors = visitors[:2000]
    save_visitors(visitors)

# ========== 修改点6：添加调试路由 ==========
@app.route('/debug-volume')
def debug_volume():
    """调试路由：查看Volume配置状态"""
    info = []
    info.append(f"<h2>Volume 调试信息</h2>")
    info.append(f"<b>RAILWAY_VOLUME_MOUNT_PATH:</b> {os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '未设置')}")
    info.append(f"<b>UPLOAD_FOLDER 配置:</b> {app.config['UPLOAD_FOLDER']}")
    info.append(f"<b>上传目录是否存在:</b> {os.path.exists(app.config['UPLOAD_FOLDER'])}")
    
    if os.path.exists(app.config['UPLOAD_FOLDER']):
        try:
            files = os.listdir(app.config['UPLOAD_FOLDER'])
            info.append(f"<b>文件数量:</b> {len(files)}")
            if files:
                info.append("<b>最近文件:</b>")
                for f in sorted(files)[-5:]:
                    fp = os.path.join(app.config['UPLOAD_FOLDER'], f)
                    size = os.path.getsize(fp)
                    info.append(f"  - {f} ({size} bytes)")
        except Exception as e:
            info.append(f"<b>读取目录出错:</b> {str(e)}")
    
    info.append(f"<br><b>所有环境变量:</b>")
    for k, v in sorted(os.environ.items()):
        if 'VOLUME' in k or 'RAILWAY' in k:
            info.append(f"  {k}: {v}")
    
    return '<pre>' + '\n'.join(info) + '</pre>'

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
        item['likes'] = likes.get(item['id'], 0)
    return jsonify({'items': page_items, 'total': total, 'page': page, 'has_more': end < total})

@app.route('/api/categories')
def api_categories():
    return jsonify(load_data().get('categories', []))

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

@app.route('/api/like/<item_id>', methods=['POST'])
def api_like(item_id):
    likes = load_likes()
    likes[item_id] = likes.get(item_id, 0) + 1
    save_likes(likes)
    return jsonify({'success': True, 'likes': likes[item_id]})

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
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file)
    cover_filename = None
    if cover and allowed_img(cover.filename):
        cover_filename = save_upload(cover, 'cover_')
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
        'type': 'video' if is_video(filename) else 'image',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'width': int(request.form.get('width', 800)),
        'height': int(request.form.get('height', 600)),
        'sort_order': int(request.form.get('sort_order', 0)),
    }
    likes[item_id] = max(0, int(request.form.get('likes', 0)))
    save_likes(likes)
    data['items'].insert(0, item)
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
    if not file or not allowed_file(file.filename): return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file)
    for item in data['items']:
        if item['id'] == item_id:
            item['filename'] = filename
            item['type'] = 'video' if is_video(filename) else 'image'
            break
    save_data(data)
    return jsonify({'success': True, 'filename': filename})

@app.route('/admin/item/<item_id>/replace-cover', methods=['POST'])
@login_required
def admin_replace_cover(item_id):
    data = load_data()
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效图片'}), 400
    cover_filename = save_upload(file, 'cover_')
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
    start = (page - 1) * per_page
    end = start + per_page
    from collections import Counter
    from datetime import timedelta
    paths = Counter(v['path'] for v in visitors)
    ips = Counter(v['ip'] for v in visitors)
    today = datetime.now().date()
    daily = {}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).strftime('%m-%d')
        daily[d] = 0
    for v in visitors:
        try:
            k = v['time'][5:10]
            if k in daily: daily[k] += 1
        except: pass
    return jsonify({'total': len(visitors), 'visitors': visitors[start:end],
                    'has_more': end < len(visitors), 'page': page,
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
    site['theme'] = body.get('theme', site.get('theme', 'warm'))
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
    site['footer'] = request.json
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/about', methods=['PUT'])
@login_required
def admin_about():
    site = load_site()
    site['about'] = request.json
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/about/upload-image', methods=['POST'])
@login_required
def admin_about_upload_image():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename): return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'about_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

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
                ftype = 'video' if ext in {'mp4','mov','webm'} else ('image' if ext in {'png','jpg','jpeg','gif','webp'} else 'other')
                files.append({
                    'filename': fn,
                    'size': stat.st_size,
                    'type': ftype,
                    'ext': ext,
                    'refs': refs.get(fn, []),
                    'url': '/static/uploads/' + fn,
                })
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
            item['type'] = 'video' if is_video(new_filename) else 'image'
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
