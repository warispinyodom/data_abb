import os
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# กำหนด Path ทั้งโฟลเดอร์ในโปรเจกต์ ( Read-only ใน Vercel) และโฟลเดอร์ชั่วคราว (/tmp/uploads)
PROJECT_UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
TMP_UPLOAD_FOLDER = '/tmp/uploads'

# สร้างโฟลเดอร์ชั่วคราวรองรับการทำงานบน Vercel
os.makedirs(TMP_UPLOAD_FOLDER, exist_ok=True)

def get_all_files():
    """ดึงรายชื่อไฟล์ทั้งหมดจากทั้งใน Git Repository และโฟลเดอร์ชั่วคราว /tmp"""
    files = set()
    if os.path.exists(PROJECT_UPLOAD_FOLDER):
        files.update(os.listdir(PROJECT_UPLOAD_FOLDER))
    if os.path.exists(TMP_UPLOAD_FOLDER):
        files.update(os.listdir(TMP_UPLOAD_FOLDER))
    return sorted(list(files))

def find_filepath(filename):
    """ค้นหาที่อยู่จริงของไฟล์ โดยให้ความสำคัญกับไฟล์ที่แก้ไข/อัปโหลดใหม่ใน /tmp ก่อน"""
    tmp_path = os.path.join(TMP_UPLOAD_FOLDER, filename)
    if os.path.exists(tmp_path):
        return tmp_path
    
    project_path = os.path.join(PROJECT_UPLOAD_FOLDER, filename)
    if os.path.exists(project_path):
        return project_path
        
    return None

def filter_data(filepath, filters=None, limit=200):
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
                    
                    # เติมข้อมูลให้ครบในกรณีที่บางแถวมีคอลัมน์ไม่เท่ากับหัวข้อ
                    if len(row) < len(headers):
                        row += [''] * (len(headers) - len(row))
                        
                    row_dict = dict(zip(headers, row))
                    
                    # ระบบตรวจสอบเงื่อนไขหลายคอลัมน์ (Multi-column filter)
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
    warning = request.args.get('warning')
    
    if request.method == 'POST':
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        if file.filename != '':
            # บันทึกไฟล์ลงโฟลเดอร์ชั่วคราว /tmp/uploads
            filepath = os.path.join(TMP_UPLOAD_FOLDER, file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    files = get_all_files()
    return render_template('index.html', files=files, edit_mode=False, warning=warning)

@app.route('/edit/<path:filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = find_filepath(filename)
    
    if request.method == 'POST':
        content = request.form['content']
        # เมื่อแก้ไขเนื้อหา ให้บันทึกไฟล์ใหม่ลงใน /tmp/uploads เสมอ
        target_path = os.path.join(TMP_UPLOAD_FOLDER, filename)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    if not filepath or not os.path.exists(filepath):
        # หากไม่พบไฟล์ (เช่น โดน Vercel ล้าง Instance) ให้รีไดเรกต์ไปแสดง warning ในหน้า index
        return redirect(url_for('index', warning='storage'))
        
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return redirect(url_for('index', warning='storage'))

    files = get_all_files()
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<path:filename>')
def delete_file(filename):
    # ลบไฟล์ออกจาก /tmp
    tmp_path = os.path.join(TMP_UPLOAD_FOLDER, filename)
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
        
    # พยายามลบจากโปรเจกต์ (เผื่อรันในเครื่อง Local)
    project_path = os.path.join(PROJECT_UPLOAD_FOLDER, filename)
    if os.path.exists(project_path):
        try:
            os.remove(project_path)
        except OSError:
            pass # ข้ามการลบหากรันบน Vercel แล้วไฟล์หลักเป็น Read-only
            
    return redirect(url_for('index'))

@app.route('/dashboard/<path:filename>', methods=['GET'])
def dashboard(filename):
    filepath = find_filepath(filename)
    
    if not filepath or not os.path.exists(filepath):
        # ถ้าไฟล์หายไป ให้รีไดเรกต์ไปแสดงแจ้งเตือนในหน้าแรก
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