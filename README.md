# Flask Application with Jinja Templates

A simple Flask web application demonstrating Jinja2 templating features.

## Features

- **Template Inheritance**: Base template with blocks for consistent layout
- **Dynamic Content**: Passing variables from Flask routes to templates
- **Control Structures**: Loops, conditionals, and filters in Jinja2
- **Form Handling**: Contact form with POST request handling
- **Responsive Design**: CSS Grid and Flexbox layouts
- **Multiple Pages**: Home, About, Gallery, and Contact pages

## Project Structure

```
Hackathon_Platforms/
│
├── app.py                 # Main Flask application
├── requirements.txt       # Python dependencies
├── README.md             # This file
│
└── templates/            # Jinja2 templates
    ├── base.html         # Base template with navigation
    ├── index.html        # Home page
    ├── about.html        # About page with team members
    ├── gallery.html      # Image gallery with grid layout
    └── contact.html      # Contact form
```

## Installation

1. Install Python 3.x if not already installed

2. Install Flask:
```bash
pip install -r requirements.txt
```

## Running the Application

1. Run the Flask app:
```bash
python app.py
```

2. Open your browser and navigate to:
```
http://127.0.0.1:5000
```

## Jinja2 Features Demonstrated

### Template Inheritance
- `{% extends "base.html" %}` - Inherit from base template
- `{% block content %}` - Define content blocks

### Variables
- `{{ variable }}` - Display variable values
- `{{ url_for('route_name') }}` - Generate URLs

### Control Structures
- `{% for item in list %}` - Loop through lists
- `{% if condition %}` - Conditional rendering
- `{{ list|length }}` - Use filters

### Loop Variables
- `loop.index` - Current iteration (1-indexed)
- `loop.first` - First iteration check
- `loop.last` - Last iteration check

## Pages Overview

- **Home** (`/`) - Welcome page with feature overview
- **About** (`/about`) - Team information with dynamic member cards
- **Gallery** (`/gallery`) - Image grid demonstrating loops
- **Contact** (`/contact`) - Form with GET/POST handling

## Customization

Feel free to modify:
- Add more routes in `app.py`
- Create new templates in `templates/`
- Update styles in `base.html`
- Add static files (CSS, JS, images) in a `static/` folder

## License

Free to use for learning and development purposes.
