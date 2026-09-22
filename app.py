from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

# 1. กำหนดตำแหน่งเก็บไฟล์
# REPO_UPLOAD_FOLDER: สำหรับไฟล์ตัวอย่างที่ Push ขึ้น GitHub พร้อมโปรเจกต์ (Read-only)
REPO_UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')

# TMP_UPLOAD_FOLDER: สำหรับไฟล์ที่ผู้ใช้อัปโหลดใหม่บน Vercel (โฟลเดอร์ /tmp อนุญาตให้เขียนไฟล์ได้)
TMP_UPLOAD_FOLDER = '/tmp/uploads'

# สร้างโฟลเดอร์ชั่วคราวใน /tmp หากยังไม่มี
if not os.path.exists(TMP_UPLOAD_FOLDER):
    try:
        os.makedirs(TMP_UPLOAD_FOLDER, exist_ok=True)
    except Exception as e:
        print(f"Error creating temp directory: {e}")

def get_file_path(filename):
    """ ค้นหาตำแหน่งจริงของไฟล์ (เช็กใน /tmp ก่อน แล้วค่อยเช็กใน Repository) """
    tmp_path = os.path.join(TMP_UPLOAD_FOLDER, filename)
    if os.path.exists(tmp_path):
        return tmp_path
    
    repo_path = os.path.join(REPO_UPLOAD_FOLDER, filename)
    if os.path.exists(repo_path):
        return repo_path
        
    return None

def get_all_files():
    """ ดึงรายชื่อไฟล์ทั้งหมดทั้งจาก /tmp และ Repo uploads/ มาแสดงผล """
    files = set()
    
    if os.path.exists(TMP_UPLOAD_FOLDER):
        files.update(os.listdir(TMP_UPLOAD_FOLDER))
        
    if os.path.exists(REPO_UPLOAD_FOLDER):
        files.update(os.listdir(REPO_UPLOAD_FOLDER))
        
    return sorted(list(files))

def filter_data(filepath, filters=None, limit=100):
    headers = []
    data = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            if lines:
                # ใช้ Tab เป็นตัวแบ่งคอลัมน์
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
    # รับค่าการแจ้งเตือนเรื่อง Storage (ถ้าระบบ Vercel เคลียร์ไฟล์ /tmp ไปแล้ว)
    warning = request.args.get('warning')
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename != '':
            # บันทึกไฟล์ลง /tmp/uploads เพื่อให้ Vercel ยอมรับการเขียนไฟล์
            filepath = os.path.join(TMP_UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    files = get_all_files()
    return render_template('index.html', files=files, edit_mode=False, warning=warning)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = get_file_path(filename)
    
    # หากหาไฟล์ไม่เจอ (ไฟล์ใน /tmp อาจถูกลบไปแล้ว) ส่งสัญญาณเตือนไปยังหน้า index.html
    if not filepath:
        return redirect(url_for('index', warning='storage'))
    
    if request.method == 'POST':
        content = request.form['content']
        # การแก้ไขจะถูกบันทึกลง /tmp/uploads
        save_path = os.path.join(TMP_UPLOAD_FOLDER, filename)
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return redirect(url_for('index', warning='storage'))
        
    files = get_all_files()
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<filename>')
def delete_file(filename):
    filepath = get_file_path(filename)
    if filepath and os.path.exists(filepath):
        try:
            os.remove(filepath)
        except Exception as e:
            print(f"Cannot delete file: {e}")
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filepath = get_file_path(filename)
    
    # หากไม่พบไฟล์ ให้เด้งกลับหน้า index พร้อมแสดงกล่องข้อความเตือนไฟล์หายใน index.html
    if not filepath:
        return redirect(url_for('index', warning='storage'))
    
    filters = {k: v for k, v in request.args.items() if v.strip()}
    headers, data = filter_data(filepath, filters=filters, limit=200)
    
    return render_template('dashboard.html', 
                           filename=filename, 
                           headers=headers, 
                           data=data, 
                           current_filters=filters)

if __name__ == '__main__':
    app.run(debug=True)