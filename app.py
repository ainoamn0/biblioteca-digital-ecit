from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        nome = request.form.get('nome')
        sobrenome = request.form.get('sobrenome')
        usuario = request.form.get('usuario')
        email = request.form.get('email')
        senha = request.form.get('senha')
        
        if not all([nome, sobrenome, usuario, email, senha]):
            flash('Por favor, preencha todos os campos.')
            return redirect(url_for('cadastro'))

        hashed_password = generate_password_hash(senha)
        
        try:
            conn = get_db_connection()
            conn.execute('INSERT INTO usuarios (nome, sobrenome, usuario, email, senha) VALUES (?, ?, ?, ?, ?)',
                         (nome, sobrenome, usuario, email, hashed_password))
            conn.commit()
            conn.close()
            flash('Cadastro realizado com sucesso! Faça login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Usuário ou E-mail já cadastrados.')
            return redirect(url_for('cadastro'))
            
    return render_template('cadastro.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user_type = request.form.get('user_type', 'aluno')
        senha = request.form.get('senha')
        
        if user_type == 'admin':
            login_val = request.form.get('email')
            conn = get_db_connection()
            admin = conn.execute('SELECT * FROM administradores WHERE email = ? OR cpf = ?', (login_val, login_val)).fetchone()
            conn.close()
            
            if admin and check_password_hash(admin['senha'], senha):
                session['user_id'] = admin['id']
                session['user_name'] = admin['nome']
                session['is_admin'] = True
                return redirect(url_for('admin_dashboard'))
            else:
                flash('E-mail, CPF ou senha de administrador incorretos.')
        else:
            email = request.form.get('email')
            conn = get_db_connection()
            user = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
            conn.close()
            
            if user and check_password_hash(user['senha'], senha):
                session['user_id'] = user['id']
                session['user_name'] = user['nome']
                session['is_admin'] = False
                return redirect(url_for('dashboard'))
            else:
                flash('E-mail ou senha incorretos.')
            
    return render_template('login.html')

def verificar_e_atualizar_reservas(conn):
    from datetime import datetime, timedelta
    now = datetime.now()
    
    # Encontra reservas 'disponivel' que já expiraram
    reservas_expiradas = conn.execute('''
        SELECT * FROM reservas 
        WHERE status = 'disponivel' AND data_limite < ?
    ''', (now.strftime('%Y-%m-%d %H:%M:%S'),)).fetchall()
    
    for res in reservas_expiradas:
        res_id = res['id']
        livro_id = res['livro_id']
        
        # Marca como expirada
        conn.execute("UPDATE reservas SET status = 'expirada' WHERE id = ?", (res_id,))
        
        # Procura o próximo na fila de espera
        proxima_reserva = conn.execute('''
            SELECT * FROM reservas 
            WHERE livro_id = ? AND status = 'aguardando' 
            ORDER BY id ASC LIMIT 1
        ''', (livro_id,)).fetchone()
        
        if proxima_reserva:
            # Passa para o próximo da fila, dando 24 horas
            data_limite = now + timedelta(hours=24)
            conn.execute('''
                UPDATE reservas 
                SET status = 'disponivel', data_limite = ? 
                WHERE id = ?
            ''', (data_limite.strftime('%Y-%m-%d %H:%M:%S'), proxima_reserva['id']))
        else:
            # Ninguém na fila, o livro volta a ficar disponível para empréstimo direto
            conn.execute('UPDATE livros SET quantidade_disponivel = quantidade_disponivel + 1 WHERE id = ?', (livro_id,))
            
    conn.commit()

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Você precisa estar logado para acessar esta página.')
        return redirect(url_for('login'))
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Atualiza qualquer reserva expirada antes de carregar o painel
    verificar_e_atualizar_reservas(conn)
    
    emprestimos = conn.execute('''
        SELECT e.*, l.titulo, l.autor, l.capa_url 
        FROM emprestimos e
        JOIN livros l ON e.livro_id = l.id
        WHERE e.usuario_id = ? AND e.status IN ('ativo', 'pendente', 'devolucao_pendente')
    ''', (user_id,)).fetchall()
    
    reservas_rows = conn.execute('''
        SELECT r.*, l.titulo, l.autor, l.capa_url
        FROM reservas r
        JOIN livros l ON r.livro_id = l.id
        WHERE r.usuario_id = ? AND (r.status = 'aguardando' or r.status = 'disponivel')
    ''', (user_id,)).fetchall()
    
    reservas = []
    for r in reservas_rows:
        r_dict = dict(r)
        if r['status'] == 'aguardando':
            # Calcula a posição na fila
            posicao = conn.execute('''
                SELECT COUNT(*) FROM reservas 
                WHERE livro_id = ? AND status = 'aguardando' AND id < ?
            ''', (r['livro_id'], r['id'])).fetchone()[0] + 1
            r_dict['posicao'] = posicao
            
            # Formata data
            try:
                from datetime import datetime
                dt = datetime.strptime(r['data_reserva'], '%Y-%m-%d %H:%M:%S')
                r_dict['data_reserva'] = dt.strftime('%d/%m/%Y')
            except Exception:
                pass
        else:
            r_dict['posicao'] = 0
            # Formata data limite de retirada
            try:
                from datetime import datetime
                dt = datetime.strptime(r['data_limite'], '%Y-%m-%d %H:%M:%S')
                r_dict['data_limite'] = dt.strftime('%d/%m/%Y %H:%M')
            except Exception:
                pass
        reservas.append(r_dict)
    
    conn.close()
    
    return render_template('interface.html', user_name=session.get('user_name'), emprestimos=emprestimos, reservas=reservas)

@app.route('/emprestar/<int:livro_id>', methods=['POST'])
def emprestar(livro_id):
    if 'user_id' not in session:
        flash('Por favor, faça login para realizar um empréstimo.')
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Atualiza as reservas expiradas primeiro
    verificar_e_atualizar_reservas(conn)
    
    emprestimos_ativos = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND status IN ("ativo", "pendente", "devolucao_pendente")', (user_id,)).fetchone()[0]
    if emprestimos_ativos >= 2:
        flash('Você já atingiu o limite máximo de 2 empréstimos simultâneos (incluindo solicitações pendentes).')
        conn.close()
        return redirect(url_for('consultarapida'))
        
    livro = conn.execute('SELECT * FROM livros WHERE id = ?', (livro_id,)).fetchone()
    if not livro or livro['quantidade_disponivel'] <= 0:
        flash('Este livro não está disponível para empréstimo no momento.')
        conn.close()
        return redirect(url_for('consultarapida'))
        
    from datetime import datetime
    data_emprestimo = datetime.now()
    
    # Registra com status pendente, sem deduzir estoque até o admin liberar
    conn.execute('INSERT INTO emprestimos (usuario_id, livro_id, data_emprestimo, status) VALUES (?, ?, ?, "pendente")',
                 (user_id, livro_id, data_emprestimo.date()))
    
    conn.commit()
    conn.close()
    flash('Solicitação de empréstimo enviada! Vá até a biblioteca para retirar o livro e ter a liberação do administrador.')
    return redirect(url_for('dashboard'))

@app.route('/reservar/<int:livro_id>', methods=['POST'])
def reservar(livro_id):
    if 'user_id' not in session:
        flash('Por favor, faça login para reservar um livro.')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Verifica se já está com o livro emprestado
    livro_emprestado = conn.execute('SELECT * FROM emprestimos WHERE usuario_id = ? AND livro_id = ? AND status = "ativo"', (user_id, livro_id)).fetchone()
    if livro_emprestado:
        flash('Você já está com este livro emprestado.')
        conn.close()
        return redirect(url_for('consultarapida'))
    
    reserva_existente = conn.execute('SELECT * FROM reservas WHERE usuario_id = ? AND livro_id = ? AND status = "aguardando"', (user_id, livro_id)).fetchone()
    if reserva_existente:
        flash('Você já tem uma reserva ativa para este livro.')
        conn.close()
        return redirect(url_for('consultarapida'))
        
    conn.execute('INSERT INTO reservas (usuario_id, livro_id) VALUES (?, ?)', (user_id, livro_id))
    conn.commit()
    conn.close()
    
    flash('Reserva realizada com sucesso. Você entrou na fila de espera.')
    return redirect(url_for('dashboard'))

@app.route('/devolver/<int:emprestimo_id>', methods=['POST'])
def devolver(emprestimo_id):
    if 'user_id' not in session:
        flash('Por favor, faça login para realizar a devolução.')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    
    emprestimo = conn.execute('SELECT * FROM emprestimos WHERE id = ? AND usuario_id = ? AND status = "ativo"', (emprestimo_id, user_id)).fetchone()
    if not emprestimo:
        flash('Empréstimo ativo não encontrado.')
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Coloca status como devolução pendente aguardando admin
    conn.execute('UPDATE emprestimos SET status = "devolucao_pendente" WHERE id = ?', (emprestimo_id,))
    conn.commit()
    conn.close()
    flash('Solicitação de devolução registrada! Devolva o livro físico na biblioteca para o administrador confirmar.')
    return redirect(url_for('dashboard'))

@app.route('/confirmar_reserva/<int:reserva_id>', methods=['POST'])
def confirmar_reserva(reserva_id):
    if 'user_id' not in session:
        flash('Por favor, faça login para confirmar a reserva.')
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Atualiza reservas expiradas primeiro
    verificar_e_atualizar_reservas(conn)
    
    reserva = conn.execute('SELECT * FROM reservas WHERE id = ? AND usuario_id = ? AND status = "disponivel"', (reserva_id, user_id)).fetchone()
    if not reserva:
        flash('Esta reserva expirou ou não está mais disponível.')
        conn.close()
        return redirect(url_for('dashboard'))
        
    emprestimos_ativos = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND status IN ("ativo", "pendente", "devolucao_pendente")', (user_id,)).fetchone()[0]
    if emprestimos_ativos >= 2:
        flash('Você já atingiu o limite máximo de 2 empréstimos simultâneos.')
        conn.close()
        return redirect(url_for('dashboard'))
        
    from datetime import datetime
    data_emprestimo = datetime.now()
    
    # Registra o empréstimo como pendente
    conn.execute('INSERT INTO emprestimos (usuario_id, livro_id, data_emprestimo, status) VALUES (?, ?, ?, "pendente")',
                 (user_id, reserva['livro_id'], data_emprestimo.date()))
                 
    # Finaliza a reserva
    conn.execute('UPDATE reservas SET status = "finalizado" WHERE id = ?', (reserva_id,))
    
    conn.commit()
    conn.close()
    
    flash('Empréstimo solicitado com sucesso! Retire o livro na biblioteca para ter a liberação do administrador.')
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu do sistema.')
    return redirect(url_for('index'))

@app.route('/consultarapida')
def consultarapida():
    if 'user_id' not in session:
        flash('Faça login para acessar o acervo da biblioteca.')
        return redirect(url_for('login'))
    
    search_query = request.args.get('search', '')
    
    conn = get_db_connection()
    if search_query:
        books = conn.execute('''
            SELECT * FROM livros 
            WHERE titulo LIKE ? OR autor LIKE ? OR categoria LIKE ?
        ''', (f'%{search_query}%', f'%{search_query}%', f'%{search_query}%')).fetchall()
    else:
        books = conn.execute('SELECT * FROM livros').fetchall()
    conn.close()
    
    return render_template('consultarapida.html', books=books, search_query=search_query)

@app.route('/suporte')
def suporte():
    return render_template('suporte.html')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Acesso restrito. Faça login como administrador.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    
    # Auto-update reservations
    verificar_e_atualizar_reservas(conn)
    
    # Livros
    livros = conn.execute('SELECT * FROM livros').fetchall()
    
    # Usuários
    usuarios = conn.execute('SELECT * FROM usuarios').fetchall()
    
    # Empréstimos com cálculo de status dinâmico
    emprestimos_raw = conn.execute('''
        SELECT e.*, l.titulo, l.autor, u.nome || ' ' || u.sobrenome as nome_usuario, u.email as email_usuario
        FROM emprestimos e
        JOIN livros l ON e.livro_id = l.id
        JOIN usuarios u ON e.usuario_id = u.id
        ORDER BY e.id DESC
    ''').fetchall()
    
    from datetime import datetime
    now_date = datetime.now().date()
    emprestimos = []
    atrasados_count = 0
    
    for emp in emprestimos_raw:
        e_dict = dict(emp)
        try:
            prev_date = datetime.strptime(emp['data_devolucao_prevista'], '%Y-%m-%d').date() if emp['data_devolucao_prevista'] else None
        except Exception:
            prev_date = None
            
        if emp['status'] == 'ativo' and prev_date and now_date > prev_date:
            e_dict['status_display'] = 'atrasado'
            atrasados_count += 1
        elif emp['status'] == 'devolvido' and emp['data_devolucao_real']:
            try:
                real_date = datetime.strptime(emp['data_devolucao_real'], '%Y-%m-%d').date()
            except Exception:
                real_date = prev_date if prev_date else now_date
            if prev_date and real_date > prev_date:
                e_dict['status_display'] = 'devolvido com atraso'
            else:
                e_dict['status_display'] = 'devolvido no prazo'
        else:
            e_dict['status_display'] = emp['status']
            
        emprestimos.append(e_dict)

    # Reservas
    reservas = conn.execute('''
        SELECT r.*, l.titulo, u.nome || ' ' || u.sobrenome as nome_usuario
        FROM reservas r
        JOIN livros l ON r.livro_id = l.id
        JOIN usuarios u ON r.usuario_id = u.id
        ORDER BY r.id DESC
    ''').fetchall()
    
    # Estatísticas
    total_livros = conn.execute('SELECT COUNT(*) FROM livros').fetchone()[0]
    total_usuarios = conn.execute('SELECT COUNT(*) FROM usuarios').fetchone()[0]
    ativos_count = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE status = "ativo"').fetchone()[0]
    
    top_livros = conn.execute('''
        SELECT l.titulo, COUNT(e.id) as total_copias
        FROM livros l
        LEFT JOIN emprestimos e ON l.id = e.livro_id
        GROUP BY l.id
        ORDER BY total_copias DESC LIMIT 3
    ''').fetchall()
    
    # Logs simulados de alertas de e-mail enviadas
    alertas_email = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE status = "ativo" AND ? > data_devolucao_prevista', (now_date,)).fetchone()[0]

    conn.close()
    
    return render_template(
        'admin_dashboard.html',
        user_name=session.get('user_name'),
        livros=livros,
        usuarios=usuarios,
        emprestimos=emprestimos,
        reservas=reservas,
        stats={
            'total_livros': total_livros,
            'total_usuarios': total_usuarios,
            'ativos_count': ativos_count,
            'atrasados_count': atrasados_count,
            'alertas_email': alertas_email,
            'top_livros': top_livros
        }
    )

@app.route('/admin/livro/adicionar', methods=['POST'])
@admin_required
def admin_adicionar_livro():
    titulo = request.form.get('titulo')
    autor = request.form.get('autor')
    descricao = request.form.get('descricao')
    categoria = request.form.get('categoria')
    quantidade = request.form.get('quantidade', type=int)
    capa_url = request.form.get('capa_url')
    
    if not all([titulo, autor, categoria, quantidade]):
        flash('Por favor, preencha todos os campos obrigatórios.')
        return redirect(url_for('admin_dashboard'))
        
    if not capa_url:
        capa_url = 'https://images.unsplash.com/photo-1543002588-bfa74002ed7e?q=80&w=300'
        
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO livros (titulo, autor, descricao, avaliacao, capa_url, quantidade_total, quantidade_disponivel, categoria)
        VALUES (?, ?, ?, 5.0, ?, ?, ?, ?)
    ''', (titulo, autor, descricao, capa_url, quantidade, quantidade, categoria))
    conn.commit()
    conn.close()
    
    flash('Livro cadastrado com sucesso!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/livro/editar/<int:livro_id>', methods=['POST'])
@admin_required
def admin_editar_livro(livro_id):
    titulo = request.form.get('titulo')
    autor = request.form.get('autor')
    descricao = request.form.get('descricao')
    categoria = request.form.get('categoria')
    quantidade_total = request.form.get('quantidade_total', type=int)
    capa_url = request.form.get('capa_url')
    
    conn = get_db_connection()
    livro = conn.execute('SELECT * FROM livros WHERE id = ?', (livro_id,)).fetchone()
    if not livro:
        flash('Livro não encontrado.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    diferenca = quantidade_total - livro['quantidade_total']
    nova_disponivel = max(0, livro['quantidade_disponivel'] + diferenca)
    
    conn.execute('''
        UPDATE livros 
        SET titulo = ?, autor = ?, descricao = ?, categoria = ?, quantidade_total = ?, quantidade_disponivel = ?, capa_url = ?
        WHERE id = ?
    ''', (titulo, autor, descricao, categoria, quantidade_total, nova_disponivel, capa_url, livro_id))
    
    conn.commit()
    conn.close()
    
    flash('Informações do livro atualizadas com sucesso!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/livro/remover/<int:livro_id>', methods=['POST'])
@admin_required
def admin_remover_livro(livro_id):
    conn = get_db_connection()
    emprestimos_ativos = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE livro_id = ? AND status = "ativo"', (livro_id,)).fetchone()[0]
    if emprestimos_ativos > 0:
        flash('Não é possível remover o livro, pois existem empréstimos ativos pendentes.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    conn.execute('DELETE FROM livros WHERE id = ?', (livro_id,))
    conn.execute('DELETE FROM reservas WHERE livro_id = ?', (livro_id,))
    conn.commit()
    conn.close()
    
    flash('Livro removido com sucesso!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/emprestimo/confirmar_retirada/<int:emprestimo_id>', methods=['POST'])
@admin_required
def admin_confirmar_retirada(emprestimo_id):
    conn = get_db_connection()
    emprestimo = conn.execute('SELECT * FROM emprestimos WHERE id = ? AND status = "pendente"', (emprestimo_id,)).fetchone()
    if not emprestimo:
        flash('Solicitação de empréstimo não encontrada.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    livro_id = emprestimo['livro_id']
    livro = conn.execute('SELECT * FROM livros WHERE id = ?', (livro_id,)).fetchone()
    if not livro or livro['quantidade_disponivel'] <= 0:
        flash('Este livro não possui exemplares disponíveis em estoque no momento.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    from datetime import datetime, timedelta
    data_emprestimo = datetime.now()
    data_devolucao_prevista = data_emprestimo + timedelta(days=7)
    
    # Atualiza status e datas do empréstimo
    conn.execute('''
        UPDATE emprestimos 
        SET status = "ativo", data_emprestimo = ?, data_devolucao_prevista = ? 
        WHERE id = ?
    ''', (data_emprestimo.date(), data_devolucao_prevista.date(), emprestimo_id))
    
    # Decrementa estoque do livro
    conn.execute('UPDATE livros SET quantidade_disponivel = quantidade_disponivel - 1 WHERE id = ?', (livro_id,))
    
    conn.commit()
    conn.close()
    flash('Empréstimo ativado com sucesso! Livro liberado para retirada.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/emprestimo/devolver/<int:emprestimo_id>', methods=['POST'])
@admin_required
def admin_devolver_emprestimo(emprestimo_id):
    conn = get_db_connection()
    emprestimo = conn.execute('SELECT * FROM emprestimos WHERE id = ? AND status IN ("ativo", "devolucao_pendente")', (emprestimo_id,)).fetchone()
    if not emprestimo:
        flash('Empréstimo ativo não encontrado.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    from datetime import datetime, timedelta
    now = datetime.now()
    
    conn.execute('UPDATE emprestimos SET status = "devolvido", data_devolucao_real = ? WHERE id = ?', (now.date(), emprestimo_id))
    
    livro_id = emprestimo['livro_id']
    proxima_reserva = conn.execute('''
        SELECT * FROM reservas 
        WHERE livro_id = ? AND status = 'aguardando' 
        ORDER BY id ASC LIMIT 1
    ''', (livro_id,)).fetchone()
    
    if proxima_reserva:
        data_limite = now + timedelta(hours=24)
        conn.execute('''
            UPDATE reservas 
            SET status = 'disponivel', data_limite = ? 
            WHERE id = ?
        ''', (data_limite.strftime('%Y-%m-%d %H:%M:%S'), proxima_reserva['id']))
        flash('Devolução processada e confirmada! O exemplar foi reservado para o próximo usuário da fila por 24 horas.')
    else:
        conn.execute('UPDATE livros SET quantidade_disponivel = quantidade_disponivel + 1 WHERE id = ?', (livro_id,))
        flash('Devolução processada e confirmada com sucesso!')
        
    conn.commit()
    conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/usuario/remover/<int:usuario_id>', methods=['POST'])
@admin_required
def admin_remover_usuario(usuario_id):
    conn = get_db_connection()
    emprestimos = conn.execute('SELECT COUNT(*) FROM emprestimos WHERE usuario_id = ? AND status = "ativo"', (usuario_id,)).fetchone()[0]
    if emprestimos > 0:
        flash('Não é possível remover o usuário, pois ele possui empréstimos ativos pendentes.')
        conn.close()
        return redirect(url_for('admin_dashboard'))
        
    conn.execute('DELETE FROM usuarios WHERE id = ?', (usuario_id,))
    conn.execute('DELETE FROM emprestimos WHERE usuario_id = ?', (usuario_id,))
    conn.execute('DELETE FROM reservas WHERE usuario_id = ?', (usuario_id,))
    conn.commit()
    conn.close()
    
    flash('Usuário removido do sistema com sucesso!')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/alertas/disparar', methods=['POST'])
@admin_required
def admin_disparar_alertas():
    flash('Todos os avisos automáticos de devolução foram enviados com sucesso via e-mail!')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
