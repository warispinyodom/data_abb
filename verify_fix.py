import os
import tempfile
from app import app

app.config['UPLOAD_FOLDER'] = os.path.join(tempfile.gettempdir(), 'vercel_fix_test3')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
path = os.path.join(app.config['UPLOAD_FOLDER'], 'HR DATA.txt')
with open(path, 'w', encoding='utf-8') as f:
    f.write('Name\tAge\nAlice\t30\nBob\t25\n')

with app.test_client() as c:
    home = c.get('/')
    home_html = home.get_data(as_text=True)
    print('HOME', home.status_code)
    print('HAS_BRACES', '{{ f }}' in home_html)
    print('LINK_OK', '/dashboard/HR%20DATA.txt' in home_html or '/dashboard/HR DATA.txt' in home_html)

    dash = c.get('/dashboard/HR%20DATA.txt')
    dash_html = dash.get_data(as_text=True)
    print('DASH', dash.status_code)
    print('TITLE_OK', 'Dashboard' in dash_html)
    print('DATA_OK', 'Alice' in dash_html)
