#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include <omp.h>

struct Punto {
    double x;
    double y;
};

struct Celda {
    int x = 0;
    int y = 0;
    std::vector<int> puntos;
    std::vector<const Celda*> vecinas;
};

struct Indice {
    std::unordered_map<std::uint64_t, Celda> celdas;
    std::vector<const Celda*> celda_de_punto;
};

// Esta función junta las coordenadas de una celda en una sola clave.
std::uint64_t clave_celda(int x, int y) {
    return (std::uint64_t(std::uint32_t(x)) << 32) | std::uint32_t(y);
}

// Esta función lee dos coordenadas por fila y omite las filas inválidas.
std::vector<Punto> leer_csv(const std::string& ruta) {
    std::ifstream archivo(ruta);
    if (!archivo) {
        throw std::runtime_error("No se pudo abrir el CSV de entrada: " + ruta);
    }
    std::vector<Punto> puntos;
    std::string linea;
    int omitidas = 0;
    while (std::getline(archivo, linea)) {
        std::stringstream fila(linea);
        std::string sx, sy, extra;
        if (!std::getline(fila, sx, ',') || !std::getline(fila, sy, ',') ||
            std::getline(fila, extra, ',')) {
            ++omitidas;
            continue;
        }
        try {
            std::size_t fin_x = 0, fin_y = 0;
            double x = std::stod(sx, &fin_x);
            double y = std::stod(sy, &fin_y);
            if (sx.find_first_not_of(" \t\r", fin_x) != std::string::npos ||
                sy.find_first_not_of(" \t\r", fin_y) != std::string::npos ||
                !std::isfinite(x) || !std::isfinite(y)) {
                ++omitidas;
                continue;
            }
            puntos.push_back({x, y});
        } catch (const std::exception&) {
            ++omitidas;
        }
    }
    if (puntos.empty()) {
        throw std::runtime_error("El CSV no contiene puntos válidos");
    }
    if (omitidas > 0) {
        std::cerr << "Filas omitidas: " << omitidas << '\n';
    }
    return puntos;
}

// Esta función agrupa puntos en celdas del tamaño de epsilon y localiza sus celdas vecinas.
Indice construir_indice(const std::vector<Punto>& puntos, double epsilon) {
    Indice indice;
    indice.celda_de_punto.resize(puntos.size());
    double min_x = puntos[0].x, min_y = puntos[0].y;
    for (const Punto& p : puntos) {
        min_x = std::min(min_x, p.x);
        min_y = std::min(min_y, p.y);
    }
    for (std::size_t i = 0; i < puntos.size(); ++i) {
        long double posicion_x = std::floor((static_cast<long double>(puntos[i].x) - min_x) / epsilon);
        long double posicion_y = std::floor((static_cast<long double>(puntos[i].y) - min_y) / epsilon);
        if (!std::isfinite(posicion_x) || !std::isfinite(posicion_y) ||
            posicion_x >= std::numeric_limits<int>::max() - 1 ||
            posicion_y >= std::numeric_limits<int>::max() - 1) {
            throw std::runtime_error("El rango de coordenadas es demasiado grande para epsilon");
        }
        int x = int(posicion_x);
        int y = int(posicion_y);
        Celda& celda = indice.celdas[clave_celda(x, y)];
        celda.x = x;
        celda.y = y;
        celda.puntos.push_back(int(i));
        indice.celda_de_punto[i] = &celda;
    }
    for (auto& par : indice.celdas) {
        Celda& celda = par.second;
        celda.vecinas.push_back(&celda);
        for (int dx = -1; dx <= 1; ++dx) {
            for (int dy = -1; dy <= 1; ++dy) {
                if (dx == 0 && dy == 0) continue;
                auto vecina = indice.celdas.find(clave_celda(celda.x + dx, celda.y + dy));
                if (vecina != indice.celdas.end()) {
                    celda.vecinas.push_back(&vecina->second);
                }
            }
        }
    }
    return indice;
}

// Esta función comprueba si un punto tiene suficientes vecinos para ser core.
bool es_core(int i, const std::vector<Punto>& puntos, const Indice& indice,
             double epsilon, int min_samples) {
    int encontrados = 1;  // DBSCAN incluye el propio punto.
    if (encontrados >= min_samples) return true;
    for (const Celda* celda : indice.celda_de_punto[i]->vecinas) {
        for (int j : celda->puntos) {
            if (j == i) continue;
            double dx = puntos[i].x - puntos[j].x;
            double dy = puntos[i].y - puntos[j].y;
            if (std::hypot(dx, dy) <= epsilon && ++encontrados >= min_samples) {
                return true;
            }
        }
    }
    return false;
}

// Esta función busca un core de primer orden cerca de un punto no denso.
bool alcanza_core(int i, const std::vector<Punto>& puntos, const Indice& indice,
                  const std::vector<unsigned char>& core, double epsilon) {
    for (const Celda* celda : indice.celda_de_punto[i]->vecinas) {
        for (int j : celda->puntos) {
            if (!core[j]) continue;
            double dx = puntos[i].x - puntos[j].x;
            double dy = puntos[i].y - puntos[j].y;
            if (std::hypot(dx, dy) <= epsilon) return true;
        }
    }
    return false;
}

// Esta función hace las dos pasadas sobre todos los puntos con OpenMP.
void clasificar(const std::vector<Punto>& puntos, const Indice& indice,
               int hilos, double epsilon, int min_samples,
               std::vector<unsigned char>& core, std::vector<unsigned char>& etiqueta) {
    int n = int(puntos.size());
    #pragma omp parallel for schedule(static) num_threads(hilos)
    for (int i = 0; i < n; ++i) {
        core[i] = es_core(i, puntos, indice, epsilon, min_samples);
    }
    #pragma omp parallel for schedule(static) num_threads(hilos)
    for (int i = 0; i < n; ++i) {
        etiqueta[i] = core[i] ? 1 :
            (alcanza_core(i, puntos, indice, core, epsilon) ? 2 : 0);
    }
}

// Esta función escribe x,y,etiqueta con 0 para ruido y 1 para cualquier core.
void escribir_csv(const std::string& ruta, const std::vector<Punto>& puntos,
                  const std::vector<unsigned char>& etiqueta) {
    std::ofstream archivo(ruta);
    if (!archivo) throw std::runtime_error("No se pudo escribir: " + ruta);
    archivo << std::setprecision(std::numeric_limits<double>::max_digits10);
    for (std::size_t i = 0; i < puntos.size(); ++i) {
        archivo << puntos[i].x << ',' << puntos[i].y << ',' << (etiqueta[i] ? 1 : 0) << '\n';
    }
}

// Esta función resume las etiquetas para detectar diferencias entre versiones.
std::uint64_t resumen(const std::vector<unsigned char>& etiqueta,
                      int& primeros, int& segundos, int& ruido) {
    primeros = segundos = ruido = 0;
    std::uint64_t hash = 1469598103934665603ULL;
    for (unsigned char valor : etiqueta) {
        if (valor == 1) ++primeros;
        else if (valor == 2) ++segundos;
        else ++ruido;
        hash = (hash ^ valor) * 1099511628211ULL;
    }
    return hash;
}

// Esta función lee un entero y rechaza caracteres sobrantes.
int leer_entero(const char* texto) {
    std::string valor(texto);
    std::size_t fin = 0;
    int numero = std::stoi(valor, &fin);
    if (fin != valor.size()) throw std::runtime_error("Entero inválido: " + valor);
    return numero;
}

// Esta función lee un número real y rechaza caracteres sobrantes.
double leer_real(const char* texto) {
    std::string valor(texto);
    std::size_t fin = 0;
    double numero = std::stod(valor, &fin);
    if (fin != valor.size()) throw std::runtime_error("Número real inválido: " + valor);
    return numero;
}

// Esta función valida los argumentos, mide las repeticiones y guarda la salida.
int main(int argc, char* argv[]) {
    try {
        if (argc != 9) {
            std::cerr << "Uso: ./dbscan_p1 entrada.csv salida.csv p1 hilos k epsilon min_samples repeticiones\n";
            return 1;
        }
        std::string entrada = argv[1], salida = argv[2], modo = argv[3];
        int hilos = leer_entero(argv[4]), k = leer_entero(argv[5]);
        double epsilon = leer_real(argv[6]);
        int min_samples = leer_entero(argv[7]), repeticiones = leer_entero(argv[8]);
        if (modo != "p1" ||
            hilos < 1 || k < 1 || !std::isfinite(epsilon) || epsilon <= 0 ||
            min_samples < 1 || repeticiones < 1) {
            throw std::runtime_error("Argumentos inválidos");
        }
        std::vector<Punto> puntos = leer_csv(entrada);
        if (puntos.size() > std::size_t(std::numeric_limits<int>::max())) {
            throw std::runtime_error("Demasiados puntos para índices de tipo int");
        }
        Indice indice = construir_indice(puntos, epsilon);
        std::vector<unsigned char> core(puntos.size()), etiqueta(puntos.size());
        omp_set_dynamic(0);
        std::cout << "iteracion,segundos,core_primero,core_segundo,ruido,hash\n";
        for (int repeticion = 1; repeticion <= repeticiones; ++repeticion) {
            auto inicio = std::chrono::steady_clock::now();
            clasificar(puntos, indice, hilos, epsilon, min_samples, core, etiqueta);
            auto fin = std::chrono::steady_clock::now();
            int primeros, segundos, ruido;
            std::uint64_t hash = resumen(etiqueta, primeros, segundos, ruido);
            double segundos_ejecucion = std::chrono::duration<double>(fin - inicio).count();
            std::cout << repeticion << ',' << std::setprecision(9) << segundos_ejecucion
                      << ',' << primeros << ',' << segundos << ',' << ruido << ',' << hash << '\n';
        }
        if (salida != "-") escribir_csv(salida, puntos, etiqueta);
    } catch (const std::exception& error) {
        std::cerr << "Error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
