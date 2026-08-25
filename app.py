from flask import Flask, render_template, request

app = Flask(__name__)


class _StripVercelPrefix:
    """On Vercel, the catch-all rewrite in vercel.json delivers every request
    with PATH_INFO set to its destination (/api/index) instead of the URL the
    browser asked for. Restore the real path so routes match. No-op locally
    and for any path that isn't prefixed."""

    _PREFIXES = ("/api/index.py", "/api/index")

    def __init__(self, wsgi_app):
        self._wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        for prefix in self._PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                environ["PATH_INFO"] = path[len(prefix):] or "/"
                break
        return self._wsgi_app(environ, start_response)


app.wsgi_app = _StripVercelPrefix(app.wsgi_app)

@app.route('/')
def home():
    return render_template('index.html', title='Home')

@app.route('/about')
def about():
    team_members = [
        {'name': 'Alice Johnson', 'role': 'Lead Developer'},
        {'name': 'Bob Smith', 'role': 'Designer'},
        {'name': 'Charlie Brown', 'role': 'Product Manager'}
    ]
    return render_template('about.html', title='About Us', team=team_members)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')
        return render_template('contact.html', 
                             title='Contact', 
                             submitted=True, 
                             name=name)
    return render_template('contact.html', title='Contact', submitted=False)

@app.route('/gallery')
def gallery():
    images = [
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'Beautiful Landscape'},
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'City Skyline'},
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'Mountain View'},
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'Ocean Waves'},
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'Forest Path'},
        {'url': 'https://via.placeholder.com/300x200', 'caption': 'Desert Sunset'}
    ]
    return render_template('gallery.html', title='Gallery', images=images)

if __name__ == '__main__':
    app.run(debug=True)
