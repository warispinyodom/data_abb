from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# เปลี่ยน UPLOAD_FOLDER ไปใช้ /tmp เพราะ Vercel อนุญาตให้เขียนไฟล์ชั่วคราวได้ที่นี่เท่านั้น
UPLOAD_FOLDER = '/tmp/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# สร้างโฟลเดอร์หากยังไม่มี
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def filter_data(filepath, search_query=None):
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                headers = lines[0].strip().split('\t')
                for line in lines[1:]:
                    if not line.strip():
                        continue
                    row = line.strip().split('\t')
                    if len(row) < len(headers):
                        row.extend([''] * (len(headers) - len(row)))
                    
                    row_dict = dict(zip(headers, row))
                    
                    if search_query:
                        search_lower = search_query.lower()
                        if any(search_lower in str(val).lower() for val in row_dict.values()):
                            data.append(row_dict)
                    else:
                        data.append(row_dict)
    except Exception as e:
        print(f"Error reading file: {e}")
    return data

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename != '':
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    # อ่านไฟล์จาก /tmp/uploads
    files = os.listdir(app.config['UPLOAD_FOLDER']) if os.path.exists(app.config['UPLOAD_FOLDER']) else []
    return render_template('index.html', files=files, edit_mode=False)

@app.route('/edit/<path:filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if request.method == 'POST':
        content = request.form['content']
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return redirect(url_for('index'))
        
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<path:filename>')
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('index'))

@app.route('/dashboard/<path:filename>')
def dashboard(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        return "ไม่พบไฟล์ (ไฟล์อาจถูกลบไปแล้วโดยระบบของ Vercel)", 404
        
    search_query = request.args.get('search', '').strip()
    data = filter_data(filepath, search_query)
    
    return render_template('dashboard.html', data=data, filename=filename, search_query=search_query)

# จุดนี้สำคัญสำหรับ Vercel ต้องให้ตัวแปร app พร้อมถูกเรียกใช้งาน
if __name__ == '__main__':
    app.run(debug=True)