from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# กำหนดตำแหน่งโฟลเดอร์ uploads หลักในเครื่อง (Local Storage)
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# สร้างโฟลเดอร์ uploads อัตโนมัติหากยังไม่มี
if not os.path.exists(UPLOAD_FOLDER):
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
            # บันทึกไฟล์ลงในโฟลเดอร์ /uploads
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    # ดึงรายชื่อไฟล์ทั้งหมดจากโฟลเดอร์ /uploads
    files = os.listdir(app.config['UPLOAD_FOLDER']) if os.path.exists(app.config['UPLOAD_FOLDER']) else []
    return render_template('index.html', files=sorted(files), edit_mode=False)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if request.method == 'POST':
        content = request.form['content']
        # บันทึกเนื้อหาใหม่ทับไฟล์เดิมใน /uploads
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    if not os.path.exists(filepath):
        return redirect(url_for('index'))

    # อ่านเนื้อหาไฟล์จาก /uploads
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    files = os.listdir(app.config['UPLOAD_FOLDER']) if os.path.exists(app.config['UPLOAD_FOLDER']) else []
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=sorted(files))

@app.route('/delete/<filename>')
def delete_file(filename):
    # ลบไฟล์ออกจากโฟลเดอร์ /uploads โดยตรง
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if not os.path.exists(filepath):
        files = os.listdir(app.config['UPLOAD_FOLDER']) if os.path.exists(app.config['UPLOAD_FOLDER']) else []
        return render_template('index.html', files=sorted(files), edit_mode=False, warning='storage')
        
    filters = {k: v for k, v in request.args.items() if v.strip()}
    headers, data = filter_data(filepath, filters=filters, limit=200)
    
    return render_template('dashboard.html', 
                           filename=filename, 
                           headers=headers, 
                           data=data, 
                           current_filters=filters)

if __name__ == '__main__':
    app.run(debug=True)