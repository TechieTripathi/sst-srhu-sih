# Flask Jinja2 Demo Application

A simple Flask application demonstrating Jinja2 templating features.

## Features

- **Template Inheritance**: Base template with blocks for consistent layout
- **Dynamic Content**: Passing variables from Flask routes to templates
- **Control Structures**: Loops, conditionals, and filters in Jinja2
- **Form Handling**: Contact form with POST request handling
- **Responsive Design**: CSS Grid and Flexbox layouts
- **Multiple Pages**: Home, About, Gallery, and Contact pages

## Project Structure

```
demo_app/
│
├── app.py                 # Main Flask application
├── README.md             # This file
│
└── templates/            # Jinja2 templates
    ├── base.html         # Base template with navigation
    ├── index.html        # Home page
    ├── about.html        # About page with team members
    ├── gallery.html      # Image gallery with grid layout
    └── contact.html      # Contact form
```

## Running the Demo App

1. Navigate to the demo_app directory:
```bash
cd demo_app
```

2. Run the Flask app (uses port 5001 to avoid conflicts):
```bash
python app.py
```

3. Open your browser and navigate to:
```
http://127.0.0.1:5001
```

## Jinja2 Features Demonstrated

### Template Inheritance
- `{% extends "base.html" %}` - Inherit from base template
- `{% block content %}` - Define content blocks
- `{% block extra_styles %}` - Additional CSS blocks

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

## Integration with Main App

This demo app runs separately on port 5001 to avoid conflicts with your main hackathon application (port 5000). You can study the Jinja2 patterns here and apply them to your main application.

## License

Free to use for learning and development purposes.
