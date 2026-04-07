import os
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import feedparser

# ===== CACHE =====
article_cache = {}
cache_time = {}

def get_cached_articles(feeds):
    articles = []
    for feed in feeds:
        if feed.id in article_cache:
            age = datetime.now() - cache_time[feed.id]
            if age < timedelta(minutes=15):
                articles.extend(article_cache[feed.id])
                continue
        try:
            parsed = feedparser.parse(feed.url)
            feed_articles = []
            for entry in parsed.entries[:4]:
                import re
                summary = entry.get('summary', '')
                summary = re.sub(r'<[^>]+>', '', summary)  # Remove HTML tags
                if len(summary) > 250:
                    summary = summary[:250] + '...'
                feed_articles.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', '#'),
                    'summary': summary,
                    'feed_name': feed.name,
                    'feed_type': feed.feed_type,
                    'category': feed.category,
                    'published': entry.get('published', 'Recent')
                })
            article_cache[feed.id] = feed_articles
            cache_time[feed.id] = datetime.now()
            articles.extend(feed_articles)
        except Exception as e:
            print(f"Error fetching {feed.name}: {e}")
    return articles

# ===== APP SETUP =====
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'feedhub-secret-123')
database_url = os.environ.get('DATABASE_URL', 'sqlite:///feedhub.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ===== MODELS =====
follows = db.Table('follows',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('feed_id', db.Integer, db.ForeignKey('feed.id'))
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    followed = db.relationship('Feed', secondary=follows, backref='followers')

class Feed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))
    url = db.Column(db.String(300))
    website = db.Column(db.String(300))
    category = db.Column(db.String(50))
    feed_type = db.Column(db.String(20))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ===== ROUTES =====
@app.route("/")
def home():
    return redirect(url_for("main_app"))
@app.route("/app")
def main_app():
    feeds_blog = Feed.query.filter_by(feed_type="blog").all()
    feeds_podcast = Feed.query.filter_by(feed_type="podcast").all()
    feeds_youtube = Feed.query.filter_by(feed_type="youtube").all()
    feeds_rss = Feed.query.filter_by(feed_type="rss").all()

    followed_ids = []
    followed_blogs = []
    followed_podcasts = []
    followed_youtube = []
    followed_rss = []
    articles = []

    if current_user.is_authenticated:
        followed_ids = [f.id for f in current_user.followed]
        followed_blogs = [f for f in current_user.followed if f.feed_type == "blog"]
        followed_podcasts = [f for f in current_user.followed if f.feed_type == "podcast"]
        followed_youtube = [f for f in current_user.followed if f.feed_type == "youtube"]
        followed_rss = [f for f in current_user.followed if f.feed_type == "rss"]
        rss_feeds = [f for f in current_user.followed if f.feed_type in ["rss", "blog"]]
        articles = get_cached_articles(rss_feeds)

    return render_template("main.html",
        feeds_blog=feeds_blog,
        feeds_podcast=feeds_podcast,
        feeds_youtube=feeds_youtube,
        feeds_rss=feeds_rss,
        followed_ids=followed_ids,
        followed_blogs=followed_blogs,
        followed_podcasts=followed_podcasts,
        followed_youtube=followed_youtube,
        followed_rss=followed_rss,
        articles=articles,
        total=len(current_user.followed) if current_user.is_authenticated else 0
    )

@app.route("/blogs")
def blogs():
    feeds = Feed.query.filter_by(feed_type="blog").all()
    followed_ids = [f.id for f in current_user.followed] if current_user.is_authenticated else []
    return render_template("blogs.html", feeds=feeds, followed_ids=followed_ids)

@app.route("/podcasts")
def podcasts():
    feeds = Feed.query.filter_by(feed_type="podcast").all()
    followed_ids = [f.id for f in current_user.followed] if current_user.is_authenticated else []
    return render_template("podcast.html", feeds=feeds, followed_ids=followed_ids)

@app.route("/youtube")
def youtube():
    feeds = Feed.query.filter_by(feed_type="youtube").all()
    followed_ids = [f.id for f in current_user.followed] if current_user.is_authenticated else []
    return render_template("youtube.html", feeds=feeds, followed_ids=followed_ids)

@app.route("/rss")
def rss():
    feeds = Feed.query.filter_by(feed_type="rss").all()
    followed_ids = [f.id for f in current_user.followed] if current_user.is_authenticated else []
    return render_template("rss.html", feeds=feeds, followed_ids=followed_ids)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("main_app"))
        flash("Invalid email or password!")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("Email already registered!")
            return redirect(url_for("register"))
        if User.query.filter_by(username=username).first():
            flash("Username already taken!")
            return redirect(url_for("register"))
        is_first = User.query.count() == 0
        user = User(username=username, email=email,
                    password=generate_password_hash(password), is_admin=is_first)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))

@app.route("/dashboard")
@login_required
def dashboard():
    followed_blogs = [f for f in current_user.followed if f.feed_type == "blog"]
    followed_podcasts = [f for f in current_user.followed if f.feed_type == "podcast"]
    followed_youtube = [f for f in current_user.followed if f.feed_type == "youtube"]
    followed_rss = [f for f in current_user.followed if f.feed_type == "rss"]
    return render_template("dashboard.html",
        followed_blogs=followed_blogs,
        followed_podcasts=followed_podcasts,
        followed_youtube=followed_youtube,
        followed_rss=followed_rss,
        total=len(current_user.followed)
    )

@app.route("/myfeeds")
@login_required
def myfeeds():
    followed_blogs = [f for f in current_user.followed if f.feed_type == "blog"]
    followed_podcasts = [f for f in current_user.followed if f.feed_type == "podcast"]
    followed_youtube = [f for f in current_user.followed if f.feed_type == "youtube"]
    followed_rss = [f for f in current_user.followed if f.feed_type == "rss"]
    rss_feeds = [f for f in current_user.followed if f.feed_type in ["rss", "blog"]]
    articles = get_cached_articles(rss_feeds)
    return render_template("myfeeds.html",
        followed_blogs=followed_blogs,
        followed_podcasts=followed_podcasts,
        followed_youtube=followed_youtube,
        followed_rss=followed_rss,
        articles=articles,
        total=len(current_user.followed)
    )

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.username = request.form.get("username", current_user.username)
        new_password = request.form.get("new_password")
        if new_password:
            current_user.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Profile updated!")
    return render_template("profile.html", user=current_user)

@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for("home"))
    users = User.query.all()
    feeds = Feed.query.all()
    return render_template("admin.html", users=users, feeds=feeds)

@app.route("/admin/add_feed", methods=["POST"])
@login_required
def add_feed():
    if not current_user.is_admin:
        return redirect(url_for("home"))
    feed = Feed(
        name=request.form.get("name"),
        description=request.form.get("description"),
        url=request.form.get("url"),
        website=request.form.get("website"),
        category=request.form.get("category"),
        feed_type=request.form.get("feed_type")
    )
    db.session.add(feed)
    db.session.commit()
    flash("Feed added!")
    return redirect(url_for("admin"))

@app.route("/admin/delete_feed/<int:feed_id>")
@login_required
def delete_feed(feed_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    feed = Feed.query.get_or_404(feed_id)
    db.session.delete(feed)
    db.session.commit()
    flash("Feed deleted!")
    return redirect(url_for("admin"))

@app.route("/admin/toggle_admin/<int:user_id>")
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    return redirect(url_for("admin"))

@app.route("/follow/<int:feed_id>", methods=["POST"])
@login_required
def follow(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    if feed in current_user.followed:
        current_user.followed.remove(feed)
        db.session.commit()
        return jsonify({"status": "unfollowed"})
    else:
        current_user.followed.append(feed)
        db.session.commit()
        return jsonify({"status": "followed"})

@app.route("/reader")
@login_required
def reader():
    articles = []
    for feed in current_user.followed:
        try:
            parsed = feedparser.parse(feed.url)
            for entry in parsed.entries[:3]:
                articles.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', '#'),
                    'summary': entry.get('summary', '')[:200],
                    'feed_name': feed.name
                })
        except:
            pass
    return render_template("reader.html", articles=articles)

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    user = User.query.filter_by(email=data.get('email')).first()
    if user and check_password_hash(user.password, data.get('password', '')):
        login_user(user)
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Invalid email or password!"})

@app.route("/api/register", methods=["POST"])
def api_register():
    data = request.get_json()
    if User.query.filter_by(email=data.get('email')).first():
        return jsonify({"success": False, "message": "Email already registered!"})
    if User.query.filter_by(username=data.get('username')).first():
        return jsonify({"success": False, "message": "Username already taken!"})
    is_first = User.query.count() == 0
    u = User(username=data['username'], email=data['email'],
             password=generate_password_hash(data['password']), is_admin=is_first)
    db.session.add(u)
    db.session.commit()
    return jsonify({"success": True, "message": "Account created! Please log in."})

# ===== SEED DATA =====
def seed_data():
    if Feed.query.count() > 0:
        return
    feeds = [
        # BLOGS - Technology
        Feed(name="TechCrunch", description="Latest tech news and startup stories", url="https://techcrunch.com/feed", website="https://techcrunch.com", category="Technology", feed_type="blog"),
        Feed(name="The Verge", description="Technology, science, art and culture", url="https://www.theverge.com/rss/index.xml", website="https://www.theverge.com", category="Technology", feed_type="blog"),
        Feed(name="Wired", description="In-depth tech and culture coverage", url="https://www.wired.com/feed/rss", website="https://www.wired.com", category="Technology", feed_type="blog"),
        Feed(name="Ars Technica", description="Technology news and analysis", url="https://feeds.arstechnica.com/arstechnica/index", website="https://arstechnica.com", category="Technology", feed_type="blog"),
        Feed(name="Engadget", description="Consumer electronics and gadgets", url="https://www.engadget.com/rss.xml", website="https://www.engadget.com", category="Technology", feed_type="blog"),
        Feed(name="Hacker News", description="Tech news from Y Combinator", url="https://news.ycombinator.com/rss", website="https://news.ycombinator.com", category="Technology", feed_type="blog"),
        Feed(name="MIT Technology Review", description="Tech from the world's top research university", url="https://www.technologyreview.com/feed/", website="https://www.technologyreview.com", category="Technology", feed_type="blog"),
        Feed(name="ZDNet", description="Technology news, analysis and advice", url="https://www.zdnet.com/news/rss.xml", website="https://www.zdnet.com", category="Technology", feed_type="blog"),
        Feed(name="VentureBeat", description="AI, AR and enterprise tech news", url="https://feeds.feedburner.com/venturebeat/SZYF", website="https://venturebeat.com", category="Technology", feed_type="blog"),
        Feed(name="Mashable Tech", description="Tech news for digital culture", url="https://mashable.com/feeds/rss/tech", website="https://mashable.com/tech", category="Technology", feed_type="blog"),

        # BLOGS - Business
        Feed(name="Harvard Business Review", description="Management and business strategy", url="https://hbr.org/feed", website="https://hbr.org", category="Business", feed_type="blog"),
        Feed(name="Forbes", description="Business, investing and entrepreneurship", url="https://www.forbes.com/innovation/feed/", website="https://www.forbes.com", category="Business", feed_type="blog"),
        Feed(name="Inc. Magazine", description="Advice for growing companies", url="https://www.inc.com/rss", website="https://www.inc.com", category="Business", feed_type="blog"),
        Feed(name="Entrepreneur", description="Business ideas and startup advice", url="https://www.entrepreneur.com/latest.rss", website="https://www.entrepreneur.com", category="Business", feed_type="blog"),
        Feed(name="Fast Company", description="Innovation in technology and business", url="https://www.fastcompany.com/latest/rss", website="https://www.fastcompany.com", category="Business", feed_type="blog"),
        Feed(name="Business Insider", description="Business news and market trends", url="https://feeds.businessinsider.com/custom/all", website="https://www.businessinsider.com", category="Business", feed_type="blog"),
        Feed(name="Bloomberg", description="Global business and finance news", url="https://feeds.bloomberg.com/technology/news.rss", website="https://www.bloomberg.com", category="Business", feed_type="blog"),

        # BLOGS - Science
        Feed(name="NASA", description="Space exploration and science", url="https://www.nasa.gov/rss/dyn/breaking_news.rss", website="https://www.nasa.gov", category="Science", feed_type="blog"),
        Feed(name="Scientific American", description="Science news and discoveries", url="https://rss.sciam.com/ScientificAmerican-Global", website="https://www.scientificamerican.com", category="Science", feed_type="blog"),
        Feed(name="New Scientist", description="Latest science and tech discoveries", url="https://www.newscientist.com/feed/home", website="https://www.newscientist.com", category="Science", feed_type="blog"),
        Feed(name="Nature News", description="International science journal", url="https://www.nature.com/nature.rss", website="https://www.nature.com", category="Science", feed_type="blog"),
        Feed(name="Science Daily", description="Latest science research news", url="https://www.sciencedaily.com/rss/all.xml", website="https://www.sciencedaily.com", category="Science", feed_type="blog"),
        Feed(name="Phys.org", description="Physics and technology news", url="https://phys.org/rss-feed/", website="https://phys.org", category="Science", feed_type="blog"),

        # BLOGS - Design 
        Feed(name="Smashing Magazine", description="Web design and development", url="https://www.smashingmagazine.com/feed", website="https://www.smashingmagazine.com", category="Design", feed_type="blog"),
        Feed(name="CSS-Tricks", description="CSS and frontend web design tips", url="https://css-tricks.com/feed", website="https://css-tricks.com", category="Design", feed_type="blog"),
        Feed(name="Designmodo", description="Web design news and tutorials", url="https://designmodo.com/feed", website="https://designmodo.com", category="Design", feed_type="blog"),
        Feed(name="A List Apart", description="Web design and standards", url="https://alistapart.com/main/feed", website="https://alistapart.com", category="Design", feed_type="blog"),
        Feed(name="UX Collective", description="UX design and research", url="https://uxdesign.cc/feed", website="https://uxdesign.cc", category="Design", feed_type="blog"),
        Feed(name="Awwwards", description="Best web design inspiration", url="https://www.awwwards.com/blog/feed", website="https://www.awwwards.com", category="Design", feed_type="blog"),

        # BLOGS - Health
        Feed(name="NHS News", description="Health news from the NHS", url="https://www.nhs.uk/news/latest-stories/rss-feed", website="https://www.nhs.uk/news", category="Health", feed_type="blog"),
        Feed(name="Everyday Health", description="Health and wellness news", url="https://www.everydayhealth.com/rss/latest-health-news.xml", website="https://www.everydayhealth.com", category="Health", feed_type="blog"),
        Feed(name="Mindbodygreen", description="Mindful health and wellness", url="https://www.mindbodygreen.com/rss.xml", website="https://www.mindbodygreen.com", category="Health", feed_type="blog"),
        Feed(name="Verywell Health", description="Evidence-based health information", url="https://www.verywellhealth.com/rss", website="https://www.verywellhealth.com", category="Health", feed_type="blog"),
        Feed(name="Healthline", description="Medical information and news", url="https://www.healthline.com/rss/health-news", website="https://www.healthline.com", category="Health", feed_type="blog"),
        Feed(name="WebMD", description="Medical news and health advice", url="https://rss.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC", website="https://www.webmd.com", category="Health", feed_type="blog"),

        # BLOGS - Education
        Feed(name="EdSurge", description="Education technology news", url="https://www.edsurge.com/articles.rss", website="https://www.edsurge.com", category="Education", feed_type="blog"),
        Feed(name="TED Blog", description="Ideas worth spreading", url="https://blog.ted.com/feed", website="https://blog.ted.com", category="Education", feed_type="blog"),
        Feed(name="Edutopia", description="K-12 education strategies", url="https://www.edutopia.org/rss.xml", website="https://www.edutopia.org", category="Education", feed_type="blog"),
        Feed(name="Inside Higher Ed", description="Higher education news", url="https://www.insidehighered.com/rss/feed/news", website="https://www.insidehighered.com", category="Education", feed_type="blog"),
        Feed(name="Times Higher Education", description="Global university rankings and news", url="https://www.timeshighereducation.com/rss.xml", website="https://www.timeshighereducation.com", category="Education", feed_type="blog"),

        # PODCASTS
        Feed(name="Lex Fridman Podcast", description="Conversations about AI, science and humanity", url="https://lexfridman.com/feed/podcast/", website="https://lexfridman.com/podcast", category="Technology", feed_type="podcast"),
        Feed(name="How I Built This", description="Entrepreneurs and their companies", url="https://feeds.npr.org/510313/podcast.xml", website="https://www.npr.org/podcasts/510313/how-i-built-this", category="Business", feed_type="podcast"),
        Feed(name="The Daily", description="Daily news from The New York Times", url="https://feeds.simplecast.com/54nAGcIl", website="https://www.nytimes.com/column/the-daily", category="News", feed_type="podcast"),
        Feed(name="Stuff You Should Know", description="Learn something new every day", url="https://omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/A91018A4-EA4F-4130-BF55-AE270180C327/44710ECC-10BB-48D1-93C7-AE270180C33F/podcast.rss", website="https://www.iheart.com/podcast/105-stuff-you-should-know-26940277/", category="Education", feed_type="podcast"),
        Feed(name="Planet Money", description="The economy explained", url="https://feeds.npr.org/510289/podcast.xml", website="https://www.npr.org/podcasts/510289/planet-money", category="Business", feed_type="podcast"),
        Feed(name="Freakonomics Radio", description="Hidden side of everything", url="https://feeds.simplecast.com/Y8lFbOT4", website="https://freakonomics.com/podcast/", category="Business", feed_type="podcast"),
        Feed(name="TED Talks Daily", description="Ideas worth spreading", url="https://feeds.feedburner.com/tedtalks_audio", website="https://www.ted.com/talks", category="Education", feed_type="podcast"),
        Feed(name="Science Vs", description="Science vs fads and popular beliefs", url="https://feeds.megaphone.fm/sciencevs", website="https://gimletmedia.com/shows/science-vs", category="Science", feed_type="podcast"),
        Feed(name="Radiolab", description="Big questions about science and philosophy", url="https://feeds.feedburner.com/radiolab/XKVq", website="https://radiolab.org", category="Science", feed_type="podcast"),
        Feed(name="The Tim Ferriss Show", description="World-class performers and their habits", url="https://rss.art19.com/tim-ferriss-show", website="https://tim.blog/podcast/", category="Business", feed_type="podcast"),

        # YOUTUBE
        Feed(name="Kurzgesagt", description="Animated science and philosophy", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q", website="https://www.youtube.com/@kurzgesagt", category="Science", feed_type="youtube"),
        Feed(name="Veritasium", description="Science and engineering videos", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCHnyfMqiRRG1u-2MsSQLbXA", website="https://www.youtube.com/@veritasium", category="Science", feed_type="youtube"),
        Feed(name="3Blue1Brown", description="Math and visual explanations", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCYO_jab_esuFRV4b17AJtAg", website="https://www.youtube.com/@3blue1brown", category="Education", feed_type="youtube"),
        Feed(name="Mark Rober", description="Engineering and science projects", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCY1kMZp36IQSyNx_9h4mpCg", website="https://www.youtube.com/@markrober", category="Science", feed_type="youtube"),
        Feed(name="TED", description="Ideas worth spreading", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCAuUUnT6oDeKwE6v1NGQxug", website="https://www.youtube.com/@TED", category="Education", feed_type="youtube"),
        Feed(name="Google", description="Official Google channel", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCVHFbw7woebKtfvug_a9dkQ", website="https://www.youtube.com/@Google", category="Technology", feed_type="youtube"),
        Feed(name="Fireship", description="Fast-paced coding tutorials", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA", website="https://www.youtube.com/@Fireship", category="Technology", feed_type="youtube"),
        Feed(name="ColdFusion", description="Technology and business stories", url="https://www.youtube.com/feeds/videos.xml?channel_id=UC4QZ_LsYcvcq7qOsOhpAX4A", website="https://www.youtube.com/@ColdFusion", category="Technology", feed_type="youtube"),
        Feed(name="MKBHD", description="High quality tech reviews", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCBJycsmduvYEL83-_4zu5EA", website="https://www.youtube.com/@mkbhd", category="Technology", feed_type="youtube"),
        Feed(name="Linus Tech Tips", description="PC hardware and tech reviews", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCXuqSBlHAE6Xw-yeJA0Tunw", website="https://www.youtube.com/@LinusTechTips", category="Technology", feed_type="youtube"),

        # RSS FEEDS
        Feed(name="BBC News", description="International news from the BBC", url="https://feeds.bbci.co.uk/news/rss.xml", website="https://www.bbc.com/news", category="News", feed_type="rss"),
        Feed(name="Reuters", description="World news and analysis", url="https://feeds.reuters.com/reuters/topNews", website="https://www.reuters.com", category="News", feed_type="rss"),
        Feed(name="Al Jazeera", description="Global news and analysis", url="https://www.aljazeera.com/xml/rss/all.xml", website="https://www.aljazeera.com", category="News", feed_type="rss"),
        Feed(name="The Guardian", description="Independent journalism", url="https://www.theguardian.com/world/rss", website="https://www.theguardian.com", category="News", feed_type="rss"),
        Feed(name="NPR News", description="Public radio news", url="https://feeds.npr.org/1001/rss.xml", website="https://www.npr.org", category="News", feed_type="rss"),
        Feed(name="Associated Press", description="Breaking news from AP", url="https://rsshub.app/apnews/topics/apf-topnews", website="https://apnews.com", category="News", feed_type="rss"),
        Feed(name="Slashdot", description="News for nerds", url="https://rss.slashdot.org/Slashdot/slashdotMain", website="https://slashdot.org", category="Technology", feed_type="rss"),
        Feed(name="GitHub Blog", description="Updates from GitHub", url="https://github.blog/feed", website="https://github.blog", category="Technology", feed_type="rss"),
        Feed(name="OpenAI Blog", description="AI research and updates", url="https://openai.com/blog/rss.xml", website="https://openai.com/blog", category="Technology", feed_type="rss"),
        Feed(name="Google AI Blog", description="Research from Google AI", url="https://blog.google/technology/ai/rss/", website="https://blog.google/technology/ai/", category="Technology", feed_type="rss"),
    ]
    db.session.bulk_save_objects(feeds)
    db.session.commit()
    print(f"Seeded {len(feeds)} feeds!")
@app.route("/api/counts")
@login_required
def api_counts():
    blogs = [f for f in current_user.followed if f.feed_type == "blog"]
    podcasts = [f for f in current_user.followed if f.feed_type == "podcast"]
    youtube = [f for f in current_user.followed if f.feed_type == "youtube"]
    rss = [f for f in current_user.followed if f.feed_type == "rss"]
    return jsonify({
        "total": len(current_user.followed),
        "blogs": len(blogs),
        "podcasts": len(podcasts),
        "youtube": len(youtube),
        "rss": len(rss),
        "articles": len(blogs) + len(rss)
    })
# Initialize database for Render deployment
with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(debug=True)