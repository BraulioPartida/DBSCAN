"""Genera datos, verifica DBSCAN, mide rendimiento y dibuja gráficas SVG."""

import argparse
import csv
import math
import os
import random
import statistics
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape


BASE = Path(__file__).resolve().parent
EJECUTABLES = {modo: BASE / f"dbscan_{modo}" for modo in ("serial", "p1", "p2")}
DATOS = BASE / "datos"
RESULTADOS = BASE / "resultados"
TAMANOS = (20000, 40000, 80000, 120000, 140000, 160000, 180000, 200000)
DIVISIONES = (2, 4, 8, 16, 32, 64)
EPSILON = 0.03
MIN_SAMPLES = 10
REPETICIONES = 10


# Esta función compila por separado las tres versiones de C++.
def compilar():
    for modo, ejecutable in EJECUTABLES.items():
        orden = ["g++", "-O2", "-std=c++17", "-fopenmp", f"dbscan_{modo}.cpp",
                 "-o", str(ejecutable)]
        subprocess.run(orden, cwd=BASE, check=True)


# Esta función crea los ocho CSV a partir de la misma serie de puntos aleatorios.
def generar_datos():
    DATOS.mkdir(exist_ok=True)
    rng = random.Random(11)
    centros = ((0.2, 0.2), (0.2, 0.8), (0.8, 0.2), (0.8, 0.8))
    archivos = {n: (DATOS / f"{n}_data.csv").open("w", newline="") for n in TAMANOS}
    escritores = {n: csv.writer(archivo) for n, archivo in archivos.items()}
    try:
        for i in range(max(TAMANOS)):
            if i % 100 == 0:
                x, y = rng.random(), rng.random()
            else:
                cx, cy = centros[i % 4]
                x, y = rng.gauss(cx, 0.06), rng.gauss(cy, 0.06)
            fila = (f"{x:.3f}", f"{y:.3f}")
            for n in TAMANOS:
                if i < n:
                    escritores[n].writerow(fila)
    finally:
        for archivo in archivos.values():
            archivo.close()


# Esta función ejecuta el programa y devuelve las mediciones de cada repetición.
def ejecutar(entrada, salida, modo, hilos, k, epsilon, min_samples, repeticiones):
    orden = [str(EJECUTABLES[modo]), str(entrada), str(salida), modo, str(hilos), str(k),
             str(epsilon), str(min_samples), str(repeticiones)]
    proceso = subprocess.run(orden, capture_output=True, text=True, check=True)
    return list(csv.DictReader(proceso.stdout.splitlines()))


# Esta función calcula directamente los vecinos para tener una referencia independiente.
def referencia(puntos, epsilon, min_samples):
    vecinos = []
    for x, y in puntos:
        vecinos.append([j for j, (a, b) in enumerate(puntos)
                        if math.hypot(x - a, y - b) <= epsilon])
    core = [len(fila) >= min_samples for fila in vecinos]
    return [1 if core[i] else (2 if any(core[j] for j in vecinos[i]) else 0)
            for i in range(len(puntos))]


# Esta función resume las etiquetas del mismo modo que el programa de C++.
def firma(etiquetas):
    hash_actual = 1469598103934665603
    for valor in etiquetas:
        hash_actual = ((hash_actual ^ valor) * 1099511628211) & ((1 << 64) - 1)
    return (etiquetas.count(1), etiquetas.count(2), etiquetas.count(0), str(hash_actual))


# Esta función compara las tres versiones con una solución directa y revisa el CSV.
def verificar():
    if not all(ruta.exists() for ruta in EJECUTABLES.values()):
        compilar()
    rng = random.Random(91)
    puntos = [(0.50, 0.50), (0.50, 0.50), (0.52, 0.50), (0.48, 0.50)]
    for centro in ((0.49, 0.49), (0.51, 0.51), (0.15, 0.85)):
        puntos.extend((round(rng.gauss(centro[0], 0.025), 3),
                       round(rng.gauss(centro[1], 0.025), 3)) for _ in range(60))
    puntos.extend((round(rng.random(), 3), round(rng.random(), 3)) for _ in range(30))
    esperado = referencia(puntos, EPSILON, MIN_SAMPLES)
    firma_esperada = firma(esperado)
    with tempfile.TemporaryDirectory() as carpeta:
        entrada = Path(carpeta) / "entrada.csv"
        salida = Path(carpeta) / "salida.csv"
        with entrada.open("w", newline="") as archivo:
            csv.writer(archivo).writerows(puntos)
        casos = [("serial", 1, 1)] + [("p1", h, 1) for h in (1, 2, 4)]
        casos += [("p2", h, k) for k in DIVISIONES for h in (1, 2, 4)]
        for modo, hilos, k in casos:
            filas = ejecutar(entrada, salida, modo, hilos, k, EPSILON, MIN_SAMPLES, 1)
            fila = filas[0]
            obtenida = (int(fila["core_primero"]), int(fila["core_segundo"]),
                        int(fila["ruido"]), fila["hash"])
            with salida.open(newline="") as archivo:
                etiquetas = [int(r[2]) for r in csv.reader(archivo)]
            if obtenida != firma_esperada or etiquetas != [int(x > 0) for x in esperado]:
                raise AssertionError(f"Falló {modo}, hilos={hilos}, k={k}")
    print(f"Verificación correcta: {len(casos)} configuraciones y {len(puntos)} puntos.")


# Esta función guarda las diez mediciones de cada configuración y comprueba sus etiquetas.
def medir():
    if not all(ruta.exists() for ruta in EJECUTABLES.values()):
        compilar()
    if any(not (DATOS / f"{n}_data.csv").exists() for n in TAMANOS):
        generar_datos()
    RESULTADOS.mkdir(exist_ok=True)
    virtuales = os.cpu_count() or 1
    hilos_posibles = tuple(dict.fromkeys((1, max(1, virtuales // 2), virtuales, 2 * virtuales)))
    ruta_crudos = RESULTADOS / "tiempos_crudos.csv"
    columnas = ("n", "version", "k", "hilos", "iteracion", "segundos",
                "core_primero", "core_segundo", "ruido", "hash")
    with ruta_crudos.open("w", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        for n in TAMANOS:
            entrada = DATOS / f"{n}_data.csv"
            esperada = None
            configuraciones = [("serial", 0, 1)]
            configuraciones += [("p1", 0, h) for h in hilos_posibles]
            configuraciones += [("p2", k, h) for k in DIVISIONES for h in hilos_posibles]
            for modo, k, hilos in configuraciones:
                filas = ejecutar(entrada, "-", modo, hilos, max(1, k), EPSILON,
                                 MIN_SAMPLES, REPETICIONES)
                if len(filas) != REPETICIONES:
                    raise AssertionError("Faltan repeticiones")
                for fila in filas:
                    actual = (fila["core_primero"], fila["core_segundo"],
                              fila["ruido"], fila["hash"])
                    if esperada is None:
                        esperada = actual
                    if actual != esperada:
                        raise AssertionError(f"Las etiquetas difieren para N={n}, {modo}, k={k}, hilos={hilos}")
                    escritor.writerow({"n": n, "version": modo, "k": k, "hilos": hilos,
                                       **fila})
                archivo.flush()
            print(f"N={n}: {len(configuraciones)} configuraciones terminadas", flush=True)
    resumir()
    graficar()
    guardar_salidas()


# Esta función guarda un CSV de etiquetas para cada tamaño de entrada.
def guardar_salidas():
    if not all(ruta.exists() for ruta in EJECUTABLES.values()):
        compilar()
    RESULTADOS.mkdir(exist_ok=True)
    for n in TAMANOS:
        entrada = DATOS / f"{n}_data.csv"
        salida = RESULTADOS / f"{n}_results.csv"
        ejecutar(entrada, salida, "p2", os.cpu_count() or 1, 16,
                 EPSILON, MIN_SAMPLES, 1)
    print("CSV de etiquetas guardados en resultados/")


# Esta función promedia los tiempos y calcula el speedup frente a la versión serial.
def resumir():
    RESULTADOS.mkdir(exist_ok=True)
    grupos = {}
    with (RESULTADOS / "tiempos_crudos.csv").open(newline="") as archivo:
        for fila in csv.DictReader(archivo):
            clave = (int(fila["n"]), fila["version"], int(fila["k"]), int(fila["hilos"]))
            grupos.setdefault(clave, []).append(fila)
    medias = {clave: statistics.mean(float(f["segundos"]) for f in filas)
              for clave, filas in grupos.items()}
    ruta = RESULTADOS / "resumen.csv"
    columnas = ("n", "version", "k", "hilos", "repeticiones", "media_s", "desv_s",
                "speedup", "core_primero", "core_segundo", "ruido")
    with ruta.open("w", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        for clave in sorted(grupos):
            n, modo, k, hilos = clave
            filas = grupos[clave]
            tiempos = [float(f["segundos"]) for f in filas]
            base = medias.get((n, "serial", 0, 1), math.nan)
            escritor.writerow({"n": n, "version": modo, "k": k, "hilos": hilos,
                               "repeticiones": len(filas), "media_s": f"{medias[clave]:.9f}",
                               "desv_s": f"{statistics.pstdev(tiempos):.9f}",
                               "speedup": f"{base / medias[clave]:.4f}",
                               "core_primero": filas[0]["core_primero"],
                               "core_segundo": filas[0]["core_segundo"],
                               "ruido": filas[0]["ruido"]})
    print(f"Resumen guardado en {ruta}")


# Esta función dibuja una gráfica sencilla de speedup en formato SVG.
def crear_svg(ruta, titulo, paneles, series, hilos_posibles):
    columnas = 2 if len(paneles) > 1 else 1
    filas = math.ceil(len(paneles) / columnas)
    ancho_panel, alto_panel = (650, 310) if columnas == 2 else (900, 440)
    ancho, alto = columnas * ancho_panel + 40, filas * alto_panel + 100
    maximo = max(1.8, max((valor for puntos in series.values() for valor in puntos.values()), default=1))
    limite = math.ceil(maximo * 1.1)
    colores = {1: "#666666", 8: "#2878b5", 16: "#df7f13", 32: "#39834f"}
    lineas = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" '
              f'viewBox="0 0 {ancho} {alto}">',
              '<rect width="100%" height="100%" fill="white"/>',
              f'<text x="{ancho / 2}" y="35" text-anchor="middle" font-size="23">{escape(titulo)}</text>']
    for indice, panel in enumerate(paneles):
        ox = 45 + (indice % columnas) * ancho_panel
        oy = 65 + (indice // columnas) * alto_panel
        izquierda, arriba = ox + 60, oy + 35
        graf_ancho, graf_alto = ancho_panel - 110, alto_panel - 105
        lineas.append(f'<text x="{izquierda}" y="{oy + 18}" font-size="18">{escape(panel)}</text>')
        lineas.append(f'<path d="M {izquierda} {arriba} V {arriba + graf_alto} H {izquierda + graf_ancho}" '
                       'fill="none" stroke="#333"/>')
        for valor in (0, 1, 1.5, limite):
            y = arriba + graf_alto * (1 - valor / limite)
            lineas.append(f'<line x1="{izquierda}" y1="{y:.1f}" x2="{izquierda + graf_ancho}" '
                          f'y2="{y:.1f}" stroke="{("#bb5555" if valor == 1.5 else "#dddddd")}" '
                          'stroke-dasharray="4 4"/>')
            lineas.append(f'<text x="{izquierda - 8}" y="{y + 4:.1f}" text-anchor="end" '
                          f'font-size="12">{valor:g}</text>')
        for pos, n in enumerate(TAMANOS):
            x = izquierda + graf_ancho * pos / (len(TAMANOS) - 1)
            lineas.append(f'<text x="{x:.1f}" y="{arriba + graf_alto + 18}" '
                          f'text-anchor="middle" font-size="12">{n // 1000}</text>')
        for hilos in hilos_posibles:
            puntos = series.get((panel, hilos), {})
            color = colores.get(hilos, "#8956a6")
            coordenadas = []
            for pos, n in enumerate(TAMANOS):
                if n not in puntos:
                    continue
                x = izquierda + graf_ancho * pos / (len(TAMANOS) - 1)
                y = arriba + graf_alto * (1 - puntos[n] / limite)
                coordenadas.append((x, y))
            if coordenadas:
                vertices = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordenadas)
                lineas.append(f'<polyline points="{vertices}" fill="none" stroke="{color}" stroke-width="2"/>')
                lineas.extend(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"/>'
                              for x, y in coordenadas)
        lineas.append(f'<text x="{izquierda + graf_ancho / 2}" y="{arriba + graf_alto + 40}" '
                      'text-anchor="middle" font-size="13">Miles de puntos</text>')
    leyenda = "   ".join(f'<tspan fill="{colores.get(h, "#8956a6")}">● {h} hilos</tspan>'
                         for h in hilos_posibles)
    lineas.append(f'<text x="{ancho / 2}" y="{alto - 18}" text-anchor="middle" font-size="15">{leyenda}</text>')
    lineas.append('</svg>')
    ruta.write_text("\n".join(lineas), encoding="utf-8")


# Esta función crea una gráfica para P1 y otra con los seis valores de k para P2.
def graficar():
    series_p1, series_p2 = {}, {}
    hilos = set()
    with (RESULTADOS / "resumen.csv").open(newline="") as archivo:
        for fila in csv.DictReader(archivo):
            n, k, h = int(fila["n"]), int(fila["k"]), int(fila["hilos"])
            if fila["version"] == "p1":
                series_p1.setdefault(("P1: dominio completo", h), {})[n] = float(fila["speedup"])
                hilos.add(h)
            elif fila["version"] == "p2":
                series_p2.setdefault((f"P2: k={k}", h), {})[n] = float(fila["speedup"])
                hilos.add(h)
    hilos = sorted(hilos)
    crear_svg(RESULTADOS / "speedup_p1.svg", "Speedup de P1 respecto a serial",
              ["P1: dominio completo"], series_p1, hilos)
    crear_svg(RESULTADOS / "speedup_p2.svg", "Speedup de P2 respecto a serial",
              [f"P2: k={k}" for k in DIVISIONES], series_p2, hilos)
    print("Gráficas SVG guardadas en resultados/")


# Esta función selecciona la actividad solicitada desde la terminal.
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("accion", choices=("compilar", "generar", "verificar", "medir", "resumir", "graficar", "salidas", "todo"))
    args = parser.parse_args()
    if args.accion in ("compilar", "todo"):
        compilar()
    if args.accion in ("generar", "todo"):
        generar_datos()
    if args.accion in ("verificar", "todo"):
        verificar()
    if args.accion in ("medir", "todo"):
        medir()
    if args.accion == "resumir":
        resumir()
    if args.accion == "graficar":
        graficar()
    if args.accion == "salidas":
        guardar_salidas()


if __name__ == "__main__":
    main()
