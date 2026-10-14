import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify
import pyodbc

app = Flask(__name__)

# --- CONFIGURACIÓN Y BASE DE DATOS ---
def obtener_conexion():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=localhost\\SQLEXPRESS;'  # Si usas SQL Server Express, cambia a: 'SERVER=localhost\\SQLEXPRESS;'
        'DATABASE=SalonDB;'
        'Trusted_Connection=yes;'
    )

# ==========================================
# 1. RUTAS DE CLIENTA (PÚBLICAS)
# ==========================================

# Página principal: Formulario de reserva
@app.route('/')
def index():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("SELECT * FROM Servicios")
        servicios = cursor.fetchall()
        cursor.execute("SELECT * FROM Trabajadoras")
        trabajadoras = cursor.fetchall()
        conexion.close()
        return render_template('index.html', servicios=servicios, trabajadoras=trabajadoras)
    except Exception as e:
        return f"Error al cargar la página principal: {e}"

@app.route('/agendar', methods=['POST'])
def agendar():
    try:
        nombre = request.form['nombre']
        telefono = request.form['telefono']
        servicio_id = request.form['servicio_id']
        trabajadora_id = request.form['trabajadora_id']
        fecha = request.form['fecha']
        hora = request.form['hora']

        # Combinar fecha y hora para la columna fecha_hora obligatoria
        fecha_hora_combinada = f"{fecha} {hora}"

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        # Incluimos 'fecha_hora' en las columnas y en los valores
        cursor.execute("""
            INSERT INTO citas (nombre_cliente, telefono_cliente, id_servicio, trabajadoras_idTrabajadora, fecha, hora, fecha_hora, estado)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente')
        """, (nombre, telefono, servicio_id, trabajadora_id, fecha, hora, fecha_hora_combinada))

        conexion.commit()
        conexion.close()

        return render_template('exito.html', nombre=nombre, fecha=fecha, hora=hora)

    except Exception as e:
        print("Error al agendar:", e)
        return f"Ocurrió un error al guardar la cita: {e}", 500

# API para obtener las horas disponibles dinámicamente con AJAX
@app.route('/horas_disponibles', methods=['GET'])
def horas_disponibles():
    id_trabajadora = request.args.get('trabajadora_id')
    fecha = request.args.get('fecha')
    
    if not id_trabajadora or not fecha:
        return jsonify({"exito": False, "horas": []})
        
    horarios_base = ["08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
    
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # Obtenemos las horas ocupadas o bloqueadas para esa especialista en esa fecha
        cursor.execute("""
            SELECT hora FROM citas 
            WHERE trabajadoras_idTrabajadora = ? AND fecha = ? AND estado != 'Cancelada'
        """, (int(id_trabajadora), fecha))
        
        raw_ocupadas = cursor.fetchall()
        conexion.close()
        
        ocupadas = []
        for row in raw_ocupadas:
            if row[0]:
                hora_str = str(row[0]).strip()[:5]
                ocupadas.append(hora_str)
                
        libres = [h for h in horarios_base if h not in ocupadas]
        
        return jsonify({"exito": True, "horas": libres})
    except Exception as e:
        print(f"Error en /horas_disponibles: {e}")
        return jsonify({"exito": False, "error": str(e)}), 500

# Consultar citas pendientes por número de teléfono de la clienta
@app.route('/mis_citas', methods=['GET', 'POST'])
def mis_citas():
    citas = []
    telefono = ""
    if request.method == 'POST':
        telefono = request.form.get('telefono', '').strip()
        if telefono:
            conexion = obtener_conexion()
            cursor = conexion.cursor()
            query = """
                SELECT 
                    c.idcitas,
                    c.nombre_cliente,
                    c.telefono_cliente,
                    s.nombre AS servicio,
                    t.nombre AS trabajadora,
                    c.fecha,
                    c.hora,
                    c.estado
                FROM citas c
                JOIN Servicios s ON c.id_servicio = s.id
                JOIN Trabajadoras t ON c.trabajadoras_idTrabajadora = t.idTrabajadora
                WHERE c.telefono_cliente = ? AND c.estado = 'Pendiente'
                ORDER BY c.fecha ASC, c.hora ASC
            """
            cursor.execute(query, (telefono,))
            raw_citas = cursor.fetchall()
            
            for row in raw_citas:
                row_list = list(row)
                if row_list[6]:
                    try:
                        hora_str = str(row_list[6])[:5]
                        hora_12 = datetime.datetime.strptime(hora_str, "%H:%M").strftime("%I:%M %p")
                        row_list[6] = hora_12
                    except:
                        pass
                citas.append(row_list)
            conexion.close()
            
    return render_template('buscar_cita.html', citas=citas, telefono=telefono)

# Cancelación efectuada por la clienta (Redirige a /mis_citas)
@app.route('/cancelar_cita_cliente/<int:id_cita>', methods=['POST'])
def cancelar_cita_cliente(id_cita):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM citas WHERE idcitas = ?", (id_cita,))
        conexion.commit()
        conexion.close()
        return redirect(url_for('mis_citas'))
    except Exception as e:
        return f"Error al cancelar la cita: {e}"


# ==========================================
# 2. RUTAS DE ADMINISTRACIÓN
# ==========================================

# Panel principal del administrador
@app.route('/admin')
def admin():
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        # Marca automáticamente como 'Finalizada' las citas que ya pasaron
        cursor.execute("""
            UPDATE citas 
            SET estado = 'Finalizada' 
            WHERE fecha_hora < GETDATE() AND estado = 'Pendiente'
        """)
        conexion.commit()
        
        cursor.execute("SELECT * FROM Trabajadoras")
        trabajadoras = cursor.fetchall()
        
        query = """
            SELECT 
                c.idcitas,
                c.nombre_cliente,
                c.telefono_cliente,
                s.nombre AS servicio,
                t.nombre AS trabajadora,
                c.fecha,
                c.hora,
                c.estado
            FROM citas c
            JOIN Servicios s ON c.id_servicio = s.id
            JOIN Trabajadoras t ON c.trabajadoras_idTrabajadora = t.idTrabajadora
            ORDER BY c.fecha DESC, c.hora DESC
        """
        cursor.execute(query)
        raw_citas = cursor.fetchall()
        
        citas = []
        for row in raw_citas:
            row_list = list(row)
            if row_list[6]:
                try:
                    hora_str = str(row_list[6])[:5]
                    hora_12 = datetime.datetime.strptime(hora_str, "%H:%M").strftime("%I:%M %p")
                    row_list[6] = hora_12
                except:
                    pass
            citas.append(row_list)
            
        conexion.close()
        return render_template('admin.html', citas=citas, trabajadoras=trabajadoras)
    except Exception as e:
        return f"Error al cargar el panel de administración: {e}"

# Bloqueo manual de horarios por especialista desde el panel admin
@app.route('/bloquear_horario', methods=['POST'])
def bloquear_horario():
    try:
        id_trabajadora = request.form['trabajadora_id']
        fecha = request.form['fecha']
        hora = request.form['hora']
        
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        
        fecha_hora = f"{fecha} {hora}:00" if len(hora) == 5 else f"{fecha} {hora}"
        
        cursor.execute("""
            INSERT INTO citas (nombre_cliente, telefono_cliente, id_servicio, trabajadoras_idTrabajadora, fecha, hora, fecha_hora, estado)
            VALUES ('HORARIO BLOQUEADO', 'N/A', (SELECT TOP 1 id FROM Servicios), ?, ?, ?, ?, 'Bloqueado')
        """, (id_trabajadora, fecha, hora, fecha_hora))
        
        conexion.commit()
        conexion.close()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Error al bloquear horario: {e}"

# Eliminación/Cancelación realizada desde el panel del Administrador
@app.route('/cancelar_cita/<int:id_cita>', methods=['POST'])
def cancelar_cita(id_cita):
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        cursor.execute("DELETE FROM citas WHERE idcitas = ?", (id_cita,))
        conexion.commit()
        conexion.close()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Error al eliminar la cita: {e}"


# ==========================================
# 3. PUNTO DE ENTRADA DE LA APLICACIÓN
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)