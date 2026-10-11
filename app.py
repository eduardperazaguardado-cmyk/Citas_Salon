from flask import Flask, render_template, request, jsonify, redirect
import pyodbc

app = Flask(__name__)

def obtener_conexion():
    conexion = pyodbc.connect(
        'driver={odbc driver 17 for sql server};'
        'server= .\SQLEXPRESS;'
        'database=SalonDB;'
        'trusted_connection=yes;'
    )

    return conexion
from flask import Flask, render_template

# ... (tu configuración de conexión se queda igual)

@app.route('/')
def inicio():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute(""" SELECT idServicio, nombre, descripcion, precio, duracion_minutos 
                           FROM Servicios 
                           WHERE activo = 1 
                           ORDER BY nombre """)
        servicios = cursor.fetchall()
        cursor.close()
        conexion.close()
        
        # Enviamos los servicios desde la base de datos hacia tu nuevo archivo HTML
        return render_template('index.html', servicios=servicios)

    except Exception as error:
        return f"Error al conectar con la base de datos: {error}", 500
    
@app.route('/agendar', methods=['POST'])
def agendar():
    try:
        # 1. Recibimos los datos (ahora fecha y hora vienen listos y por separado)
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        servicio_id = request.form['servicio']
        fecha_sola = request.form['fecha']
        hora_sola = request.form['hora']

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        # --- ESCUDO DE VALIDACIÓN: Verificamos si la hora ya está tomada ---
        cursor.execute("""
            SELECT idcitas FROM citas 
            WHERE fecha = ? AND hora = ? AND estado != 'cancelada'
        """, (fecha_sola, hora_sola))
        
        cita_existente = cursor.fetchone()
        
        # Si SQL Server encuentra un registro, rechazamos la nueva cita
        if cita_existente:
            cursor.close()
            conexion.close()
            return f"""
            <div style="text-align: center; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin-top: 50px;">
                <h2 style="color: #e11d48;">¡Ups! Ese horario ya está ocupado. 😅</h2>
                <p>Alguien más ya reservó un espacio el <b>{fecha_sola}</b> a las <b>{hora_sola}</b>.</p>
                <a href="/" style="padding: 10px 20px; background-color: #fb7185; color: white; text-decoration: none; border-radius: 8px;">Elegir otra hora</a>
            </div>
            """
        # -------------------------------------------------------------------

        # 2. Si el horario está libre, guardamos la cita en tu tabla
        cursor.execute("""
            INSERT INTO citas (nombre_cliente, telefono_cliente, id_servicio, fecha, hora)
            VALUES (?, ?, ?, ?, ?)
        """, (nombre, telefono, servicio_id, fecha_sola, hora_sola))
        
        # 3. Confirmamos los cambios
        conexion.commit() 
        cursor.close()
        conexion.close()

        # 4. Mostramos la página de éxito decorada
        return render_template('exito.html')

    except Exception as error:
        return f"Error al guardar la cita: {error}", 500

@app.route('/horas_disponibles')
def horas_disponibles():
    # Recibimos la fecha que la clienta eligió en el calendario
    fecha = request.args.get('fecha')
    if not fecha:
        return jsonify([])

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    
    # Buscamos qué horas ya están ocupadas en esa fecha exacta
    cursor.execute("SELECT hora FROM citas WHERE fecha = ? AND estado != 'cancelada'", (fecha,))
    citas_tomadas = cursor.fetchall()
    
    # Guardamos las horas ocupadas en una lista (formato "14:00")
    horas_ocupadas = []
    for cita in citas_tomadas:
        hora_str = str(cita[0])[:5] 
        horas_ocupadas.append(hora_str)
        
    cursor.close()
    conexion.close()

    # Esta es tu lista de todas las horas que atiende el salón
    todas_las_horas = [
        "08:00", "09:00", "10:00", "11:00", 
        "12:00", "13:00", "14:00", "15:00", "16:00",
        "17:00", "18:00", "19:00"
    ]

    # La magia: filtramos y dejamos SOLO las horas que NO están ocupadas
    horas_libres = [h for h in todas_las_horas if h not in horas_ocupadas]

    return jsonify(horas_libres)

@app.route('/admin')
def admin():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # El WHERE oculta las canceladas y terminadas de la vista de la Jefa
        cursor.execute("""
            SELECT c.idcitas, c.nombre_cliente, c.telefono_cliente, s.nombre, c.fecha, c.hora, c.estado 
            FROM citas c
            JOIN servicios s ON c.id_servicio = s.idservicio
            WHERE c.estado NOT IN ('cancelada', 'cancelado', 'Terminada')
            ORDER BY c.fecha, c.hora
        """)
        citas_agendadas = cursor.fetchall()
        
        cursor.close()
        conexion.close()
        
        return render_template('admin.html', citas=citas_agendadas)

    except Exception as error:
        return f"Error al cargar el panel de administración: {error}", 500
    
@app.route('/bloquear', methods=['POST'])
def bloquear():
    try:
        fecha_bloqueo = request.form['fecha']
        hora_bloqueo = request.form['hora']

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        # Obtenemos cualquier ID de servicio válido para que SQL Server no dé error
        cursor.execute("SELECT TOP 1 idservicio FROM servicios")
        servicio_dummy = cursor.fetchone()[0]

        # Insertamos la cita fantasma
        cursor.execute("""
            INSERT INTO citas (nombre_cliente, telefono_cliente, id_servicio, fecha, hora, estado)
            VALUES ('BLOQUEADO / PERSONAL', 'N/A', ?, ?, ?, 'Bloqueado')
        """, (servicio_dummy, fecha_bloqueo, hora_bloqueo))
        
        conexion.commit()
        cursor.close()
        conexion.close()

        # Recargamos la página del admin para ver los cambios
        return redirect('/admin')

    except Exception as error:
        return f"Error al bloquear el horario: {error}", 500
    
@app.route('/cancelar', methods=['POST'])
def cancelar():
    try:
        # Recibimos el ID de la cita que tu prima quiere cancelar
        id_cita = request.form['id_cita']
        
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # Cambiamos el estado a 'cancelado' (así liberamos el espacio)
        cursor.execute("""
            UPDATE citas 
            SET estado = 'cancelado' 
            WHERE idcitas = ?
        """, (id_cita,))
        
        conexion.commit()
        cursor.close()
        conexion.close()
        
        # Recargamos la página del admin
        return redirect('/admin')

    except Exception as error:
        return f"Error al cancelar la cita: {error}", 500
@app.route('/mis_citas', methods=['GET', 'POST'])
def mis_citas():
    try:
        # Si la clienta envía el formulario con su teléfono
        if request.method == 'POST':
            telefono = request.form['telefono']
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            
            # Buscamos SOLO las citas que no estén canceladas ni bloqueadas
            cursor.execute("""
                SELECT c.idcitas, s.nombre, c.fecha, c.hora 
                FROM citas c
                JOIN servicios s ON c.id_servicio = s.idservicio
                WHERE c.telefono_cliente = ? AND c.estado NOT IN ('cancelada', 'cancelado', 'Bloqueado')
            """, (telefono,))
            citas_encontradas = cursor.fetchall()
            
            cursor.close()
            conexion.close()
            
            return render_template('buscar_cita.html', citas=citas_encontradas)
            
        # Si entra por primera vez a la página, mostramos el buscador vacío
        return render_template('buscar_cita.html', citas=None)
        
    except Exception as error:
        return f"Error al buscar citas: {error}", 500

@app.route('/cancelar_cliente', methods=['POST'])
def cancelar_cliente():
    try:
        id_cita = request.form['id_cita']
        
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # Le cambiamos el estado a 'cancelada'
        cursor.execute("UPDATE citas SET estado = 'cancelada' WHERE idcitas = ?", (id_cita,))
        
        conexion.commit()
        cursor.close()
        conexion.close()
        
        # Mensaje de confirmación para la clienta
        return """
        <div style="text-align: center; font-family: 'Poppins', sans-serif; margin-top: 100px;">
            <h1 style="color: #831843;">Cita cancelada con éxito ✅</h1>
            <p style="color: #6c757d; font-size: 1.2rem; margin-bottom: 30px;">Tu espacio ha sido liberado. ¡Esperamos verte pronto!</p>
            <a href="/" style="padding: 12px 25px; background-color: #fb7185; color: white; text-decoration: none; border-radius: 10px; font-weight: 500;">Volver al inicio</a>
        </div>
        """
    except Exception as error:
        return f"Error al cancelar: {error}", 500
    
@app.route('/terminar', methods=['POST'])
def terminar():
    try:
        id_cita = request.form['id_cita']
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # Cambiamos el estado a Terminada
        cursor.execute("UPDATE citas SET estado = 'Terminada' WHERE idcitas = ?", (id_cita,))
        
        conexion.commit()
        cursor.close()
        conexion.close()
        
        return redirect('/admin')
    except Exception as error:
        return f"Error al terminar la cita: {error}", 500
    
if __name__ == '__main__':
    app.run(debug=True)