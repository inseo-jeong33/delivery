from flask import Flask, render_template, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = 'apt_admin_secret_key'

# 초기 데이터: 관리자 계정은 항상 존재해야 함
users = {
    "admin": {"status": "approved", "is_admin": True}
}
orders = []

@app.route('/')
def index():
    # 1. 세션에 사용자 정보가 없으면 로그인으로
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    
    # 2. KeyError 방지: users 목록에 해당 아이디가 있는지 확인
    if user_id not in users:
        # 만약 세션은 있는데 서버 데이터에 없다면(서버 재시작 등), 로그아웃 처리
        session.clear()
        return redirect(url_for('login'))

    # 3. 관리자는 바로 통과
    if users[user_id].get('is_admin'):
        return render_template('index.html', orders=orders, user=session['user'], is_admin=True)

    # 4. 일반 유저 중 미승인 유저는 대기 화면으로
    if users[user_id].get('status') == 'pending':
        return render_template('waiting.html', user=session['user'])
        
    return render_template('index.html', orders=orders, user=session['user'], is_admin=False)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        dong = request.form.get('dong')
        ho = request.form.get('ho')
        
        # 관리자 로그인 (동 입력창에 admin 입력 시)
        if dong == 'admin':
            session['user_id'] = 'admin'
            session['user'] = '관리자'
            return redirect(url_for('index'))
        
        # 일반 주민 로그인
        user_id = f"{dong}-{ho}"
        if user_id not in users:
            # 새로운 유저 등록
            users[user_id] = {"status": "pending", "is_admin": False}
            flash('주민 등록 신청 완료! 관리자 승인을 기다려주세요.')
        
        session['user_id'] = user_id
        session['user'] = f"{dong}동 {ho}호"
        return redirect(url_for('index'))
            
    return render_template('login.html')

@app.route('/admin')
def admin_panel():
    user_id = session.get('user_id')
    # 관리자 권한 확인
    if user_id == 'admin' or (user_id in users and users[user_id].get('is_admin')):
        return render_template('admin.html', users=users)
    
    return "권한이 없습니다. 관리자 계정으로 로그인하세요.", 403

@app.route('/approve/<user_id>')
def approve_user(user_id):
    # 현재 로그인한 사람이 관리자일 때만 승인 가능
    if session.get('user_id') == 'admin':
        if user_id in users:
            users[user_id]['status'] = 'approved'
    return redirect(url_for('admin_panel'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/create', methods=['POST'])
def create_order():
    if 'user_id' not in session or users.get(session['user_id'], {}).get('status') != 'approved':
        return redirect(url_for('login'))
    
    restaurant = request.form.get('restaurant')
    min_amount = request.form.get('min_amount')
    if restaurant and min_amount:
        orders.append({
            "id": len(orders) + 1,
            "restaurant": restaurant,
            "min_amount": int(min_amount),
            "current_amount": 0,
            "leader": session['user']
        })
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)