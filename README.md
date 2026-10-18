# Proyecto: detección de ruido con DBSCAN y OpenMP

Este proyecto resuelve el algoritmo de dos pasos de la presentación: encuentra los puntos **core de primer orden**, reclasifica los puntos alcanzables desde ellos como **core de segundo orden** y deja los demás como **ruido**. Incluye una versión serial y dos versiones paralelas con OpenMP.

## Archivos

| Archivo o carpeta | Contenido |
|---|---|
| `dbscan_serial.cpp` | Versión serial completa, incluida la lectura y escritura de CSV. |
| `dbscan_p1.cpp` | Versión P1 con OpenMP sobre todos los puntos. |
| `dbscan_p2.cpp` | Versión P2 con OpenMP sobre `k` regiones. |
| `experimentos.py` | Generación de datos, comprobación independiente, 2,320 mediciones, promedios y gráficas SVG. Solo usa la biblioteca estándar de Python. |
| `DBSCAN_noise.ipynb` | Libreta original de referencia de la materia; se conserva sin cambios. |
| `ProyectoApertura2026bDBSCAN.pdf` | Presentación original del proyecto. |
| `datos/` | Ocho CSV de entrada, uno por tamaño solicitado. |
| `resultados/tiempos_crudos.csv` | Las diez mediciones de cada configuración. |
| `resultados/resumen.csv` | Promedios, desviaciones, speedups y conteos. |
| `resultados/speedup_p1.svg`, `speedup_p2.svg` | Gráficas generadas desde el resumen. |
| `resultados/*_results.csv` | Ocho salidas `x,y,etiqueta`, una por tamaño; son compatibles con el formato de la libreta. |
| `INFORME.md` | Explicación del código, experimento, equipo, resultados y uso ético de IA. |


## Requisitos y ejecución

Se necesita `g++` con OpenMP y Python 3. No hace falta instalar paquetes de Python para ejecutar `experimentos.py`.

```bash
g++ -O2 -std=c++17 -fopenmp dbscan_serial.cpp -o dbscan_serial
g++ -O2 -std=c++17 -fopenmp dbscan_p1.cpp -o dbscan_p1
g++ -O2 -std=c++17 -fopenmp dbscan_p2.cpp -o dbscan_p2
./dbscan_serial datos/20000_data.csv serial_results.csv serial 1 1 0.03 10 1
./dbscan_p1 datos/20000_data.csv p1_results.csv p1 16 1 0.03 10 1
./dbscan_p2 datos/20000_data.csv p2_results.csv p2 16 16 0.03 10 1
```

Los argumentos son:

```text
./dbscan_serial entrada.csv salida.csv serial hilos k epsilon min_samples repeticiones
./dbscan_p1 entrada.csv salida.csv p1 hilos k epsilon min_samples repeticiones
./dbscan_p2 entrada.csv salida.csv p2 hilos k epsilon min_samples repeticiones
```

Cada archivo se compila y ejecuta por separado. El argumento de modo debe corresponder al ejecutable. `serial` y `p1` no usan `k`, así que se puede pasar `1`. En `p2`, `k` indica cuántos rectángulos se usan para dividir el plano. Si `salida.csv` es `-`, no se escribe archivo; esto sirve para medir rendimiento. Cada repetición imprime su tiempo de **clasificación**, conteos de las tres categorías y un hash de etiquetas. La lectura, preparación del índice y escritura quedan fuera de ese cronómetro. El CSV de salida tiene **tres columnas sin encabezado**: `x,y,etiqueta`, donde 0 es ruido y 1 reúne ambos tipos de core, como espera la libreta.

Para rehacer el proyecto completo:

```bash
python3 experimentos.py todo
```

También se pueden ejecutar por separado las acciones `compilar`, `generar`, `verificar`, `medir`, `resumir`, `graficar` y `salidas`. `medir` realiza la matriz experimental completa y después actualiza promedios, gráficas y CSV de etiquetas. Los tamaños, `k`, `epsilon` y `min_samples` están al principio de `experimentos.py`.

## Cómo comprobar la corrección

```bash
python3 experimentos.py verificar
```

Esta acción compara las tres versiones con una implementación directa por fuerza bruta sobre puntos pequeños, incluidos duplicados y puntos cerca de divisiones. Comprueba tanto los conteos internos como las etiquetas del CSV. Durante `medir`, cada una de las 2,320 ejecuciones se compara por conteos y hash contra la versión serial del mismo conjunto de datos. El informe explica el experimento y sus límites.
