from flask import Flask, render_template, request

app = Flask(__name__)

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
    app.run(debug=True, port=5001)
