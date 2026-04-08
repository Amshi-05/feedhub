import os
import threading
from flask import Flask, render_template, redirect, url_for, request, jsonify, flash
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
                feed_articles.append({
                    'title': entry.get('title', 'No title'),
                    'link': entry.get('link', '#'),
                    'summary': entry.get('summary', '')[:200],
                    'published': entry.get('published', ''),
                    'source': feed.name,
                    'feed_type': feed.feed_type
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
    url = db.Column(db.String(500), nullable=False)
    website = db.Column(db.String(500))
    description = db.Column(db.String(500))
    category = db.Column(db.String(50))
    feed_type = db.Column(db.String(20), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ===== SEED DATA =====
def seed_data():
    if Feed.query.count() > 0:
        return
    feeds = [
        # BLOGS
        Feed(name="TechCrunch", url="https://techcrunch.com/feed/", website="https://techcrunch.com", description="Latest tech news and startup stories", category="Technology", feed_type="blog"),
        Feed(name="The Verge", url="https://www.theverge.com/rss/index.xml", website="https://www.theverge.com", description="Technology, science, art and culture", category="Technology", feed_type="blog"),
        Feed(name="Wired", url="https://www.wired.com/feed/rss", website="https://www.wired.com", description="In-depth tech and culture coverage", category="Technology", feed_type="blog"),
        Feed(name="Ars Technica", url="https://feeds.arstechnica.com/arstechnica/index", website="https://arstechnica.com", description="Technology news and analysis", category="Technology", feed_type="blog"),
        Feed(name="Engadget", url="https://www.engadget.com/rss.xml", website="https://www.engadget.com", description="Consumer electronics and gadgets", category="Technology", feed_type="blog"),
        Feed(name="Hacker News", url="https://news.ycombinator.com/rss", website="https://news.ycombinator.com", description="Technology news from Y Combinator", category="Technology", feed_type="blog"),
        Feed(name="MIT Technology Review", url="https://www.technologyreview.com/feed/", website="https://www.technologyreview.com", description="Emerging technology coverage", category="Technology", feed_type="blog"),
        Feed(name="VentureBeat", url="https://venturebeat.com/feed/", website="https://venturebeat.com", description="Technology and business news", category="Technology", feed_type="blog"),
        Feed(name="ZDNet", url="https://www.zdnet.com/news/rss.xml", website="https://www.zdnet.com", description="Technology news and analysis", category="Technology", feed_type="blog"),
        Feed(name="Harvard Business Review", url="https://hbr.org/subscribe?delivery=rss", website="https://hbr.org", description="Management and business insights", category="Business", feed_type="blog"),
        Feed(name="Inc. Magazine", url="https://www.inc.com/rss/", website="https://www.inc.com", description="Small business and entrepreneurship", category="Business", feed_type="blog"),
        Feed(name="Fast Company", url="https://www.fastcompany.com/latest/rss?truncate=0", website="https://www.fastcompany.com", description="Business, innovation and design", category="Business", feed_type="blog"),
        Feed(name="Forbes", url="https://www.forbes.com/innovation/feed2", website="https://www.forbes.com", description="Business and finance news", category="Business", feed_type="blog"),
        Feed(name="Science Daily", url="https://www.sciencedaily.com/rss/all.xml", website="https://www.sciencedaily.com", description="Latest science news", category="Science", feed_type="blog"),
        Feed(name="NASA", url="https://www.nasa.gov/rss/dyn/breaking_news.rss", website="https://www.nasa.gov", description="Space and science news", category="Science", feed_type="blog"),
        Feed(name="National Geographic", url="https://feeds.nationalgeographic.com/ng/News/News_Main", website="https://www.nationalgeographic.com", description="Science, nature and culture", category="Science", feed_type="blog"),
        Feed(name="Smashing Magazine", url="https://www.smashingmagazine.com/feed/", website="https://www.smashingmagazine.com", description="Web design and development", category="Design", feed_type="blog"),
        Feed(name="CSS-Tricks", url="https://css-tricks.com/feed/", website="https://css-tricks.com", description="CSS and web design tips", category="Design", feed_type="blog"),
        Feed(name="A List Apart", url="https://alistapart.com/main/feed/", website="https://alistapart.com", description="Web design best practices", category="Design", feed_type="blog"),
        Feed(name="Edutopia", url="https://www.edutopia.org/rss.xml", website="https://www.edutopia.org", description="Education innovation and learning", category="Education", feed_type="blog"),
        Feed(name="Khan Academy Blog", url="https://blog.khanacademy.org/feed/", website="https://blog.khanacademy.org", description="Education for everyone", category="Education", feed_type="blog"),
        Feed(name="Healthline", url="https://www.healthline.com/rss/health-news", website="https://www.healthline.com", description="Health and wellness news", category="Health", feed_type="blog"),
        Feed(name="WebMD", url="https://rssfeeds.webmd.com/rss/rss.aspx?RSSSource=RSS_PUBLIC", website="https://www.webmd.com", description="Medical and health information", category="Health", feed_type="blog"),

        # PODCASTS
        Feed(name="Lex Fridman Podcast", url="https://lexfridman.com/feed/podcast/", website="https://lexfridman.com/podcast", description="AI, science and technology conversations", category="Technology", feed_type="podcast"),
        Feed(name="How I Built This", url="https://feeds.npr.org/510313/podcast.xml", website="https://www.npr.org/podcasts/510313/how-i-built-this", description="Stories behind successful companies", category="Business", feed_type="podcast"),
        Feed(name="The Daily", url="https://feeds.simplecast.com/54nAGcIl", website="https://www.nytimes.com/column/the-daily", description="Daily news from NYT", category="News", feed_type="podcast"),
        Feed(name="Serial", url="https://feeds.serialpodcast.org/serialpodcast", website="https://serialpodcast.org", description="Investigative journalism stories", category="True Crime", feed_type="podcast"),
        Feed(name="TED Talks Daily", url="https://feeds.feedburner.com/TEDTalks_audio", website="https://www.ted.com/podcasts/tedtalks_audio", description="Ideas worth spreading", category="Education", feed_type="podcast"),
        Feed(name="Radiolab", url="https://feeds.wnyc.org/radiolab", website="https://radiolab.org", description="Science and philosophy stories", category="Science", feed_type="podcast"),
        Feed(name="Planet Money", url="https://feeds.npr.org/510289/podcast.xml", website="https://www.npr.org/podcasts/510289/planet-money", description="Economy made easy", category="Business", feed_type="podcast"),
        Feed(name="Stuff You Should Know", url="https://feeds.megaphone.fm/stuffyoushouldknow", website="https://www.iheart.com/podcast/105-stuff-you-should-know-26940277/", description="Fun facts about everything", category="Education", feed_type="podcast"),
        Feed(name="The Joe Rogan Experience", url="https://feeds.megaphone.fm/GLT1412515089", website="https://open.spotify.com/show/4rOoJ6Egrf8K2IrywzwOMk", description="Long-form conversations", category="Entertainment", feed_type="podcast"),
        Feed(name="Crime Junkie", url="https://feeds.audioboom.com/channels/4902353/feed.rss", website="https://crimejunkiepodcast.com", description="True crime stories", category="True Crime", feed_type="podcast"),
        Feed(name="Freakonomics Radio", url="https://feeds.simplecast.com/Y8lFbOT4", website="https://freakonomics.com", description="Economics of everyday life", category="Business", feed_type="podcast"),
        Feed(name="Hidden Brain", url="https://feeds.npr.org/510308/podcast.xml", website="https://hiddenbrain.org", description="Human behavior and psychology", category="Science", feed_type="podcast"),
        Feed(name="Conan O'Brien Needs a Friend", url="https://feeds.simplecast.com/dHoohVNH", website="https://www.earwolf.com/show/conan-obrien-needs-a-friend/", description="Comedy and conversations", category="Comedy", feed_type="podcast"),
        Feed(name="My Favorite Murder", url="https://feeds.megaphone.fm/myfavoritemurder", website="https://www.myfavoritemurder.com", description="Comedy true crime", category="True Crime", feed_type="podcast"),
        Feed(name="StartUp Podcast", url="https://feeds.megaphone.fm/startup", website="https://gimletmedia.com/shows/startup", description="What starting a business is really like", category="Business", feed_type="podcast"),

        # YOUTUBE
        Feed(name="Fireship", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA", website="https://www.youtube.com/@Fireship", description="Fast-paced tech tutorials", category="Technology", feed_type="youtube"),
        Feed(name="Kurzgesagt", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCsXVk37bltHxD1rDPwtNM8Q", website="https://www.youtube.com/@kurzgesagt", description="Science explained beautifully", category="Science", feed_type="youtube"),
        Feed(name="TED", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCAuUUnT6oDeKwE6v1NGQxug", website="https://www.youtube.com/@TED", description="Ideas worth spreading", category="Education", feed_type="youtube"),
        Feed(name="Mark Rober", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCY1kMZp36IQSyNx_9h4mpCg", website="https://www.youtube.com/@MarkRober", description="Science and engineering projects", category="Science", feed_type="youtube"),
        Feed(name="3Blue1Brown", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCYO_jab_esuFRV4b17AJtAg", website="https://www.youtube.com/@3blue1brown", description="Math explained visually", category="Education", feed_type="youtube"),
        Feed(name="Veritasium", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCHnyfMqiRRG1u-2MsSQLbXA", website="https://www.youtube.com/@veritasium", description="Science and engineering videos", category="Science", feed_type="youtube"),
        Feed(name="CGP Grey", url="https://www.youtube.com/feeds/videos.xml?channel_id=UC2C_jShtL725hvbm1arSV9w", website="https://www.youtube.com/@CGPGrey", description="Thought-provoking explainer videos", category="Education", feed_type="youtube"),
        Feed(name="Vsauce", url="https://www.youtube.com/feeds/videos.xml?channel_id=UC6nSFpj9HTCZ5t-N3Rm3-HA", website="https://www.youtube.com/@Vsauce", description="Mind-bending science questions", category="Science", feed_type="youtube"),
        Feed(name="Linus Tech Tips", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCXuqSBlHAE6Xw-yeJA0Tunw", website="https://www.youtube.com/@LinusTechTips", description="Tech reviews and tutorials", category="Technology", feed_type="youtube"),
        Feed(name="MKBHD", url="https://www.youtube.com/feeds/videos.xml?channel_id=UCBJycsmduvYEL83R_U4JriQ", website="https://www.youtube.com/@mkbhd", description="High quality tech reviews", category="Technology", feed_type="youtube"),
        Feed(name="Wendover Productions", url="https://www.youtube.com/feeds/videos.xml?channel_id=UC9RM-iSvTu1uPJb8X5yp3EQ", website="https://www.youtube.com/@Wendoverproductions", description="How the world works", category="Education", feed_type="youtube"),
        Feed(name="Cold Fusion", url="https://www.youtube.com/feeds/videos.xml?channel_id=UC4QZ_LsYcvcq7qOsOhpAX4A", website="https://www.youtube.com/@ColdFusion", description="Technology and science stories", category="Technology", feed_type="youtube"),

        # RSS
        Feed(name="BBC News", url="http://feeds.bbci.co.uk/news/rss.xml", website="https://www.bbc.com/news", description="Breaking news from BBC", category="News", feed_type="rss"),
        Feed(name="Reuters", url="https://feeds.reuters.com/reuters/topNews", website="https://www.reuters.com", description="Global news from Reuters", category="News", feed_type="rss"),
        Feed(name="The Guardian", url="https://www.theguardian.com/world/rss", website="https://www.theguardian.com", description="World news from The Guardian", category="News", feed_type="rss"),
        Feed(name="Al Jazeera", url="https://www.aljazeera.com/xml/rss/all.xml", website="https://www.aljazeera.com", description="Global news coverage", category="News", feed_type="rss"),
        Feed(name="Associated Press", url="https://rsshub.app/apnews/topics/apf-topnews", website="https://apnews.com", description="Breaking news from AP", category="News", feed_type="rss"),
        Feed(name="NPR News", url="https://feeds.npr.org/1001/rss.xml", website="https://www.npr.org", description="National Public Radio news", category="News", feed_type="rss"),
        Feed(name="NASA News", url="https://www.nasa.gov/rss/dyn/breaking_news.rss", website="https://www.nasa.gov/news", description="Latest from NASA", category="Science", feed_type="rss"),
        Feed(name="New Scientist", url="https://www.newscientist.com/feed/home/", website="https://www.newscientist.com", description="Science news and discoveries", category="Science", feed_type="rss"),
    ]
    for feed in feeds:
        db.session.add(feed)
    db.session.commit()

# ===== BACKGROUND FETCH =====
def background_fetch():
    while True:
        try:
            with app.app_context():
                all_feeds = Feed.query.filter(
                    Feed.feed_type.in_(['blog', 'rss'])
                ).all()
                if all_feeds:
                    get_cached_articles(all_feeds)
                    print(f"Background fetch: {len(all_feeds)} feeds updated")
        except Exception as e:
            print(f"Background fetch error: {e}")
        threading.Event().wait(900)

fetch_thread = threading.Thread(target=background_fetch, daemon=True)
fetch_thread.start()

# Initialize database
with app.app_context():
    db.create_all()
    seed_data()

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
        article_feeds = [f for f in current_user.followed if f.feed_type in ['blog', 'rss']]
        articles = get_cached_articles(article_feeds)

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

@app.route("/myfeeds")
@login_required
def myfeeds():
    followed_blogs = [f for f in current_user.followed if f.feed_type == "blog"]
    followed_podcasts = [f for f in current_user.followed if f.feed_type == "podcast"]
    followed_youtube = [f for f in current_user.followed if f.feed_type == "youtube"]
    followed_rss = [f for f in current_user.followed if f.feed_type == "rss"]
    article_feeds = [f for f in current_user.followed if f.feed_type in ['blog', 'rss']]
    articles = get_cached_articles(article_feeds)
    return render_template("myfeeds.html",
        followed_blogs=followed_blogs,
        followed_podcasts=followed_podcasts,
        followed_youtube=followed_youtube,
        followed_rss=followed_rss,
        articles=articles
    )

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
            return render_template("register.html")
        is_admin = User.query.count() == 0
        user = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            is_admin=is_admin
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for("main_app"))
    return render_template("register.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main_app"))

@app.route("/follow/<int:feed_id>", methods=["POST"])
@login_required
def follow(feed_id):
    try:
        feed = Feed.query.get_or_404(feed_id)
        if feed in current_user.followed:
            current_user.followed.remove(feed)
            db.session.commit()
            return jsonify({"status": "unfollowed"})
        else:
            current_user.followed.append(feed)
            db.session.commit()
            return jsonify({"status": "followed"})
    except Exception as e:
        db.session.rollback()
        print(f"Follow error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

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

@app.route("/api/dashboard-data")
@login_required
def dashboard_data():
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
        "blog_feeds": [{"name":f.name,"category":f.category,"website":f.website or f.url} for f in blogs],
        "podcast_feeds": [{"name":f.name,"category":f.category,"website":f.website or f.url} for f in podcasts],
        "youtube_feeds": [{"name":f.name,"category":f.category,"website":f.website or f.url} for f in youtube],
        "rss_feeds": [{"name":f.name,"category":f.category,"website":f.website or f.url} for f in rss]
    })

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
    return render_template("profile.html")

@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        return redirect(url_for("main_app"))
    users = User.query.all()
    feeds = Feed.query.all()
    return render_template("admin.html", users=users, feeds=feeds)

@app.route("/admin/add-feed", methods=["POST"])
@login_required
def add_feed():
    if not current_user.is_admin:
        return redirect(url_for("main_app"))
    feed = Feed(
        name=request.form.get("name"),
        url=request.form.get("url"),
        website=request.form.get("website"),
        description=request.form.get("description"),
        category=request.form.get("category"),
        feed_type=request.form.get("feed_type")
    )
    db.session.add(feed)
    db.session.commit()
    return redirect(url_for("admin"))

@app.route("/admin/delete-feed/<int:feed_id>")
@login_required
def delete_feed(feed_id):
    if not current_user.is_admin:
        return redirect(url_for("main_app"))
    feed = Feed.query.get_or_404(feed_id)
    db.session.delete(feed)
    db.session.commit()
    return redirect(url_for("admin"))

@app.route("/admin/toggle-admin/<int:user_id>")
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for("home"))
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    return redirect(url_for("admin"))

if __name__ == "__main__":
    app.run(debug=True)