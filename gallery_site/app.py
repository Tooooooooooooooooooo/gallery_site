from flask import Flask, render_template, request, jsonify
import json, os, uuid
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'gallery-secret-key-2024'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp4', 'mov', 'webm'}
IMG_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
DATA_FILE = 'data/content.json'
MESSAGES_FILE = 'data/messages.json'
SITE_FILE = 'data/site.json'
VISITORS_FILE = 'data/visitors.json'
LIKES_FILE = 'data/likes.json'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

def allowed_file(f): return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def allowed_img(f): return '.' in f and f.rsplit('.', 1)[1].lower() in IMG_EXTENSIONS
def is_video(f): return f.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'webm'}

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

def get_default_site():
    return {
        "site": {"title": "GALLERY · 视觉创作集", "subtitle": "记录生活之美，分享视觉灵感", "favicon": ""},
        "nav": {
            "logo": "GAL·LERY",
            "links": [
                {"label": "分类", "href": "#gallery"},
                {"label": "联系方式", "href": "#contact"},
                {"label": "自我介绍", "href": "/about"},
                {"label": "留言板", "href": "/messages"}
            ]
        },
        "hero": {
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
            "heroImage": "",
            "name": "创作者",
            "tagline": "用镜头记录世界的美好",
            "emoji": "🎨",
            "paragraphs": [
                "你好，我是这个画廊的主人。我热爱用镜头和画笔记录生活中的美好瞬间，每一件作品都承载着我对这个世界独特的感知与思考。",
                "这里汇聚了我在摄影、插画、设计等领域的探索与实践。希望这些作品能给你带来灵感，让我们在视觉的世界里相遇。",
                "我相信，美无处不在，关键在于是否有一双发现美的眼睛。"
            ],
            "skills": [
                {"label": "摄影", "value": 90},
                {"label": "插画", "value": 75},
                {"label": "设计", "value": 80}
            ],
            "socials": [
                {"label": "微博", "href": "#"},
                {"label": "Instagram", "href": "#"},
                {"label": "小红书", "href": "#"},
                {"label": "邮件联系", "href": "#"}
            ]
        },
        "contact": [
            {"icon": "📮", "title": "电子邮件", "value": "hello@gallery.example.com"},
            {"icon": "💬", "title": "微信", "value": "gallery_artist"},
            {"icon": "🌐", "title": "社交媒体", "value": "@gallery_art 各大平台"},
            {"icon": "📍", "title": "所在地", "value": "中国 · 上海"}
        ],
        "footer": {
            "brand": {"logo": "GAL·LERY", "desc": "记录生活之美，分享视觉灵感。\n每一帧都是独一无二的故事。"},
            "columns": [
                {"title": "导航", "links": [
                    {"label": "作品集", "href": "#gallery"}, {"label": "关于我", "href": "/about"},
                    {"label": "联系方式", "href": "#contact"}, {"label": "留言板", "href": "/messages"},
                    {"label": "管理后台", "href": "/admin"}
                ]},
                {"title": "关于", "links": [
                    {"label": "隐私政策", "href": "#"}, {"label": "版权声明", "href": "#"},
                    {"label": "使用条款", "href": "#"}, {"label": "RSS 订阅", "href": "#"}
                ]}
            ],
            "copyright": "© 2024 GALLERY · 视觉创作集. All Rights Reserved. · Made with ♥"
        }
    }

def load_site():
    d = load_json(SITE_FILE, None)
    if d is None:
        return get_default_site()
    if 'site' not in d:
        d['site'] = get_default_site()['site']
    # Ensure about has new fields
    if 'about' in d:
        ab = get_default_site()['about']
        for k in ab:
            if k not in d['about']:
                d['about'][k] = ab[k]
    return d

def save_site(d): save_json(SITE_FILE, d)

def save_upload(file, prefix=''):
    ext = file.filename.rsplit('.', 1)[1].lower()
    fn = prefix + str(uuid.uuid4()) + '.' + ext
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
    return fn

def record_visitor():
    """Record visitor info from request"""
    visitors = load_visitors()
    v = {
        'id': str(uuid.uuid4()),
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ip': request.remote_addr or 'unknown',
        'ua': request.headers.get('User-Agent', '')[:200],
        'path': request.path,
        'referer': request.referrer or ''
    }
    visitors.insert(0, v)
    # Keep last 2000 records
    if len(visitors) > 2000:
        visitors = visitors[:2000]
    save_visitors(visitors)

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
    category = request.args.get('category', '')
    items = data['items']
    if category:
        items = [i for i in items if i.get('category') == category]
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    # Attach like counts
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
        msg = {'id': str(uuid.uuid4()), 'name': body.get('name', '匿名'),
               'content': body.get('content', ''), 'time': datetime.now().strftime('%Y-%m-%d %H:%M'), 'approved': True}
        messages.insert(0, msg)
        save_messages(messages)
        return jsonify({'success': True, 'message': msg})
    return jsonify([m for m in load_messages() if m.get('approved', True)])

@app.route('/api/like/<item_id>', methods=['POST'])
def api_like(item_id):
    likes = load_likes()
    likes[item_id] = likes.get(item_id, 0) + 1
    save_likes(likes)
    return jsonify({'success': True, 'likes': likes[item_id]})

# ── Admin Routes ──
@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/admin/upload', methods=['POST'])
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
    item = {
        'id': item_id,
        'title': request.form.get('title', ''),
        'category': request.form.get('category', '其他'),
        'description': request.form.get('description', ''),
        'filename': filename,
        'cover': cover_filename,
        'type': 'video' if is_video(filename) else 'image',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'width': int(request.form.get('width', 800)),
        'height': int(request.form.get('height', 600)),
    }
    likes[item_id] = 0
    save_likes(likes)
    data['items'].insert(0, item)
    save_data(data)
    return jsonify({'success': True, 'item': item})

@app.route('/admin/item/<item_id>', methods=['PUT'])
def admin_edit_item(item_id):
    data = load_data()
    body = request.json
    for item in data['items']:
        if item['id'] == item_id:
            item['title'] = body.get('title', item.get('title', ''))
            item['category'] = body.get('category', item.get('category', ''))
            item['description'] = body.get('description', item.get('description', ''))
            item['width'] = int(body.get('width', item.get('width', 800)))
            item['height'] = int(body.get('height', item.get('height', 600)))
            # Update likes if provided
            if 'likes' in body:
                likes = load_likes()
                likes[item_id] = max(0, int(body['likes']))
                save_likes(likes)
            break
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/item/<item_id>/replace-file', methods=['POST'])
def admin_replace_file(item_id):
    data = load_data()
    file = request.files.get('file')
    if not file or not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file)
    for item in data['items']:
        if item['id'] == item_id:
            item['filename'] = filename
            item['type'] = 'video' if is_video(filename) else 'image'
            break
    save_data(data)
    return jsonify({'success': True, 'filename': filename})

@app.route('/admin/item/<item_id>/replace-cover', methods=['POST'])
def admin_replace_cover(item_id):
    data = load_data()
    file = request.files.get('file')
    if not file or not allowed_img(file.filename):
        return jsonify({'success': False, 'error': '无效图片'}), 400
    cover_filename = save_upload(file, 'cover_')
    for item in data['items']:
        if item['id'] == item_id:
            item['cover'] = cover_filename
            break
    save_data(data)
    return jsonify({'success': True, 'cover': cover_filename})

@app.route('/admin/delete/<item_id>', methods=['DELETE'])
def admin_delete(item_id):
    data = load_data()
    data['items'] = [i for i in data['items'] if i['id'] != item_id]
    save_data(data)
    return jsonify({'success': True})

@app.route('/admin/categories', methods=['POST'])
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
def admin_messages_list():
    return jsonify(load_messages())

@app.route('/admin/messages/delete/<msg_id>', methods=['DELETE'])
def admin_delete_message(msg_id):
    save_messages([m for m in load_messages() if m['id'] != msg_id])
    return jsonify({'success': True})

@app.route('/admin/visitors')
def admin_visitors():
    visitors = load_visitors()
    page = int(request.args.get('page', 1))
    per_page = 50
    start = (page - 1) * per_page
    end = start + per_page
    # Stats
    from collections import Counter
    paths = Counter(v['path'] for v in visitors)
    ips = Counter(v['ip'] for v in visitors)
    # Daily counts (last 14 days)
    from datetime import timedelta
    today = datetime.now().date()
    daily = {}
    for i in range(13, -1, -1):
        d = (today - timedelta(days=i)).strftime('%m-%d')
        daily[d] = 0
    for v in visitors:
        try:
            d = v['time'][:10]
            k = d[5:]  # MM-DD
            if k in daily:
                daily[k] += 1
        except: pass
    return jsonify({
        'total': len(visitors),
        'visitors': visitors[start:end],
        'has_more': end < len(visitors),
        'page': page,
        'top_pages': paths.most_common(10),
        'top_ips': ips.most_common(10),
        'daily': list(daily.items())
    })

@app.route('/admin/visitors/clear', methods=['DELETE'])
def admin_clear_visitors():
    save_visitors([])
    return jsonify({'success': True})

# Site config
@app.route('/admin/site/basic', methods=['PUT'])
def admin_site_basic():
    site = load_site()
    body = request.json
    if 'site' not in site:
        site['site'] = {}
    site['site']['title'] = body.get('title', site['site'].get('title', ''))
    site['site']['subtitle'] = body.get('subtitle', site['site'].get('subtitle', ''))
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/favicon', methods=['POST'])
def admin_site_favicon():
    site = load_site()
    file = request.files.get('file')
    if not file or not allowed_img(file.filename):
        return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'favicon_')
    if 'site' not in site:
        site['site'] = {}
    site['site']['favicon'] = filename
    save_site(site)
    return jsonify({'success': True, 'favicon': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/hero', methods=['PUT'])
def admin_hero():
    site = load_site()
    body = request.json
    site['hero']['height'] = int(body.get('height', site['hero']['height']))
    site['hero']['slides'] = body.get('slides', site['hero']['slides'])
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/hero/upload-bg', methods=['POST'])
def admin_hero_upload_bg():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename):
        return jsonify({'success': False, 'error': '无效文件'}), 400
    filename = save_upload(file, 'hero_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/nav', methods=['PUT'])
def admin_nav():
    site = load_site()
    body = request.json
    site['nav']['logo'] = body.get('logo', site['nav']['logo'])
    site['nav']['links'] = body.get('links', site['nav']['links'])
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/footer', methods=['PUT'])
def admin_footer():
    site = load_site()
    site['footer'] = request.json
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/about', methods=['PUT'])
def admin_about():
    site = load_site()
    site['about'] = request.json
    save_site(site)
    return jsonify({'success': True})

@app.route('/admin/site/about/upload-image', methods=['POST'])
def admin_about_upload_image():
    file = request.files.get('file')
    if not file or not allowed_img(file.filename):
        return jsonify({'success': False, 'error': '无效图片'}), 400
    filename = save_upload(file, 'about_')
    return jsonify({'success': True, 'filename': filename, 'url': '/static/uploads/' + filename})

@app.route('/admin/site/contact', methods=['PUT'])
def admin_contact():
    site = load_site()
    body = request.json
    site['contact'] = body.get('contact', site['contact'])
    save_site(site)
    return jsonify({'success': True})

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs('data', exist_ok=True)
    if not os.path.exists(DATA_FILE):
        save_data({"categories": ["摄影", "插画", "设计", "视频", "其他"], "items": []})
    if not os.path.exists(SITE_FILE):
        save_site(get_default_site())
    app.run(debug=True, port=5000)
