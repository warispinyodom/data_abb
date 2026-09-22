from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# กำหนดตำแหน่งโฟลเดอร์ uploads บน Server
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# สร้างโฟลเดอร์ uploads หากยังไม่มีในเครื่อง
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def filter_data(filepath, filters=None, limit=200):
    headers = []
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                headers = lines[0].strip().split('\t')
                
                for line in lines[1:]:
                    row = line.strip('\n').split('\t')
                    
                    if len(row) < len(headers):
                        row += [''] * (len(headers) - len(row))
                        
                    row_dict = dict(zip(headers, row))
                    
                    match = True
                    if filters:
                        for key, value in filters.items():
                            if value and value.lower() not in row_dict.get(key, '').lower():
                                match = False
                                break
                                
                    if match:
                        data.append(row_dict)
                        if len(data) >= limit:
                            break
    except Exception as e:
        print(f"Error reading file: {e}")
    return headers, data

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename != '':
            # บันทึกไฟล์ลงดิสก์เครื่อง Server ตรงๆ
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    # อ่านรายชื่อไฟล์ทั้งหมดจากโฟลเดอร์ uploads
    files = sorted([f for f in os.listdir(app.config['UPLOAD_FOLDER']) if not f.startswith('.')])
    return render_template('index.html', files=files, edit_mode=False)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if request.method == 'POST':
        content = request.form['content']
        # เขียนแก้ไขข้อมูลลงไฟล์บน Server
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    if not os.path.exists(filepath):
        return redirect(url_for('index'))

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    files = sorted([f for f in os.listdir(app.config['UPLOAD_FOLDER']) if not f.startswith('.')])
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<filename>')
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    # ลบไฟล์ออกจากดิสก์ของ Server
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        return redirect(url_for('index'))
        
    filters = {k: v for k, v in request.args.items() if v.strip()}
    headers, data = filter_data(filepath, filters=filters, limit=200)
    
    return render_template('dashboard.html', 
                           filename=filename, 
                           headers=headers, 
                           data=data, 
                           current_filters=filters)

if __name__ == '__main__':
    app.run(debug=True)