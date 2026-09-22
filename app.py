from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# โฟลเดอร์ uploads หลักใน Root Directory ของโปรเจกต์คุณ
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
TMP_FOLDER = '/tmp/uploads'

# สร้างโฟลเดอร์ uploads ในเครื่องถ้ายังไม่มี
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
    except OSError:
        pass

def get_active_folder():
    """เลือกโฟลเดอร์สำหรับเขียนไฟล์: ถ้าอยู่บน Vercel ให้ใช้ /tmp/uploads อัตโนมัติ"""
    if os.environ.get('VERCEL'):
        os.makedirs(TMP_FOLDER, exist_ok=True)
        return TMP_FOLDER
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    return UPLOAD_FOLDER

def find_file(filename):
    """หาตำแหน่งไฟล์ในระบบ"""
    # เช็กใน /tmp ก่อน (ไฟล์อัปโหลดใหม่บน Vercel)
    tmp_path = os.path.join(TMP_FOLDER, filename)
    if os.path.exists(tmp_path):
        return tmp_path
    
    # เช็กใน /uploads (ไฟล์ที่มีอยู่ในโปรเจกต์)
    proj_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(proj_path):
        return proj_path
        
    return None

def list_all_files():
    """ดึงรายชื่อไฟล์ทั้งหมดจากทั้งโฟลเดอร์ uploads และพื้นที่ชั่วคราว"""
    files = set()
    if os.path.exists(UPLOAD_FOLDER):
        files.update(os.listdir(UPLOAD_FOLDER))
    if os.path.exists(TMP_FOLDER):
        files.update(os.listdir(TMP_FOLDER))
    return sorted(list(files))

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
            save_dir = get_active_folder()
            filepath = os.path.join(save_dir, file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    files = list_all_files()
    return render_template('index.html', files=files, edit_mode=False)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = find_file(filename)
    
    if request.method == 'POST':
        content = request.form['content']
        save_dir = get_active_folder()
        save_path = os.path.join(save_dir, filename)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    if not filepath:
        return redirect(url_for('index'))

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    files = list_all_files()
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<filename>')
def delete_file(filename):
    """สั่งลบไฟล์ทั้งในโฟลเดอร์ uploads และพื้นที่ชั่วคราว"""
    for folder in [UPLOAD_FOLDER, TMP_FOLDER]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filepath = find_file(filename)
    
    if not filepath:
        return render_template('index.html', files=list_all_files(), edit_mode=False, warning='storage')
        
    filters = {k: v for k, v in request.args.items() if v.strip()}
    headers, data = filter_data(filepath, filters=filters, limit=200)
    
    return render_template('dashboard.html', 
                           filename=filename, 
                           headers=headers, 
                           data=data, 
                           current_filters=filters)

if __name__ == '__main__':
    app.run(debug=True)