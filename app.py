from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

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
                    
                    # เติมข้อมูลให้ครบในกรณีที่บางแถวมีคอลัมน์ไม่เท่ากับหัวข้อ
                    if len(row) < len(headers):
                        row += [''] * (len(headers) - len(row))
                        
                    row_dict = dict(zip(headers, row))
                    
                    # ระบบตรวจสอบเงื่อนไขหลายคอลัมน์ (Multi-column filter)
                    match = True
                    if filters:
                        for key, value in filters.items():
                            # ถ้าระบุค่ามา และค่าที่ค้นหาไม่ได้อยู่ในข้อมูลคอลัมน์นั้น ให้ข้ามแถวนี้ไป
                            if value and value.lower() not in row_dict.get(key, '').lower():
                                match = False
                                break
                                
                    if match:
                        data.append(row_dict)
                        # จำกัดการแสดงผลเพื่อไม่ให้เบราว์เซอร์ค้างหากข้อมูลเยอะเกินไป
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
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            return redirect(url_for('index'))
    
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', files=files, edit_mode=False)

@app.route('/edit/<filename>', methods=['GET', 'POST'])
def edit_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    if request.method == 'POST':
        content = request.form['content']
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return redirect(url_for('index'))
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    files = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', edit_mode=True, filename=filename, content=content, files=files)

@app.route('/delete/<filename>')
def delete_file(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    return redirect(url_for('index'))

@app.route('/dashboard/<filename>', methods=['GET'])
def dashboard(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    # ดึงค่าที่ผู้ใช้กรอกค้นหามาจาก URL Query String (เช่น ?Department=IT&Gender=M)
    # ตัดเอาเฉพาะ field ที่ผู้ใช้พิมพ์ข้อมูลเข้ามา
    filters = {k: v for k, v in request.args.items() if v.strip()}
    
    headers, data = filter_data(filepath, filters=filters, limit=200)
    
    return render_template('dashboard.html', 
                           filename=filename, 
                           headers=headers, 
                           data=data, 
                           current_filters=filters)

if __name__ == '__main__':
    app.run(debug=True)