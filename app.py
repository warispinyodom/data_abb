from flask import Flask, render_template, request, redirect, url_for
import os
from urllib.parse import unquote

app = Flask(__name__)

# ใช้ Absolute Path ระบุตำแหน่งโฟลเดอร์ ป้องกันปัญหา Path คลาดเคลื่อนบน Serverless
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
TMP_FOLDER = '/tmp/uploads'

# สร้างโฟลเดอร์ชั่วคราวเตรียมไว้สำหรับ Vercel
os.makedirs(TMP_FOLDER, exist_ok=True)
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    except OSError:
        pass

def get_writable_folder():
    """สลับตำแหน่งบันทึกไฟล์ไปที่ /tmp/uploads อัตโนมัติเมื่ออยู่บน Vercel"""
    if os.environ.get('VERCEL') or not os.access(UPLOAD_FOLDER, os.W_OK):
        os.makedirs(TMP_FOLDER, exist_ok=True)
        return TMP_FOLDER
    
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    return UPLOAD_FOLDER

def get_deleted_files():
    """ดึงรายชื่อไฟล์ที่ถูกระบุสถานะลบ (สำหรับจัดการไฟล์ Read-only บน Vercel)"""
    if not os.path.exists(TMP_FOLDER):
        return set()
    return {f[:-8] for f in os.listdir(TMP_FOLDER) if f.endswith('.deleted')}

def mark_as_deleted(filename):
    """ลบไฟล์จริง หรือสร้าง Marker file ใน /tmp หากเป็นไฟล์ระบบ Read-only บน Vercel"""
    # 1. ลองลบใน /tmp
    tmp_path = os.path.join(TMP_FOLDER, filename)
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # 2. ลองลบใน /uploads (ถ้าอยู่บน Vercel จะลบไม่ได้เพราะเป็น Read-Only)
    proj_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(proj_path):
        try:
            os.remove(proj_path)
        except OSError:
            # หากระบบล็อกไม่ให้ลบไฟล์ ให้สร้างไฟล์ .deleted มาร์กไว้ว่าถูกลบแล้ว
            marker_path = os.path.join(TMP_FOLDER, f"{filename}.deleted")
            try:
                with open(marker_path, 'w') as f:
                    f.write('deleted')
            except OSError:
                pass

def unmark_deleted(filename):
    """ยกเลิกสถานะลบ (กรณีมีการอัปโหลดหรือเขียนไฟล์ชื่อเดิมทับ)"""
    marker_path = os.path.join(TMP_FOLDER, f"{filename}.deleted")
    if os.path.exists(marker_path):
        try:
            os.remove(marker_path)
        except OSError:
            pass

def find_file(filename):
    """ค้นหาตำแหน่งไฟล์ รองรับ URL Decoding (%20) และ Case Sensitivity บน Linux/Vercel"""
    filename = unquote(filename)
    deleted = get_deleted_files()
    
    if filename in deleted:
        return None

    # 1. ค้นหาใน /tmp/uploads ก่อน (สำหรับไฟล์อัปโหลดใหม่หรือไฟล์ที่แก้ไข)
    tmp_path = os.path.join(TMP_FOLDER, filename)
    if os.path.exists(tmp_path):
        return tmp_path

    # 2. ค้นหาใน /uploads แบบตรงตัว
    proj_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(proj_path):
        return proj_path

    # 3. ค้นหาใน /uploads แบบไม่สนตัวพิมพ์เล็ก-ใหญ่ (สำหรับ Linux Server)
    if os.path.exists(UPLOAD_FOLDER):
        for f in os.listdir(UPLOAD_FOLDER):
            if f.lower() == filename.lower() and f not in deleted:
                return os.path.join(UPLOAD_FOLDER, f)

    return None

def list_all_files():
    """ดึงรายชื่อไฟล์ทั้งหมดที่ยังไม่ถูกลบ"""
    files = set()
    deleted = get_deleted_files()

    if os.path.exists(UPLOAD_FOLDER):
        try:
            files.update(os.listdir(UPLOAD_FOLDER))
        except OSError:
            pass

    if os.path.exists(TMP_FOLDER):
        try:
            tmp_files = [f for f in os.listdir(TMP_FOLDER) if not f.endswith('.deleted')]
            files.update(tmp_files)
        except OSError:
            pass

    active_files = [f for f in files if f not in deleted]
    return sorted(active_files)

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
            save_dir = get_writable_folder()
            filepath = os.path.join(save_dir, file.filename)
            unmark_deleted(file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    files = list_all_files()
    return render_template('index.html', files=files, edit_mode=False)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filename = unquote(filename)
    filepath = find_file(filename)
    
    if request.method == 'POST':
        content = request.form['content']
        save_dir = get_writable_folder()
        save_path = os.path.join(save_dir, filename)
        unmark_deleted(filename)
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
    filename = unquote(filename)
    mark_as_deleted(filename)
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filename = unquote(filename)
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