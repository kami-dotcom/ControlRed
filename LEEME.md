# Control de red 4.1

Descarga para Windows: [ControlRed.exe](https://github.com/kami-dotcom/ControlRed/releases/download/v4.1/ControlRed.exe) · [Todos los archivos de la versión](https://github.com/kami-dotcom/ControlRed/releases/tag/v4.1). Instala [Npcap](https://npcap.com/#download) por separado.

Aplicación local para Windows 10/11 de 64 bits con nombres de dispositivos, fabricante por MAC, búsqueda, bloqueo individual y lista blanca por red.

## Versión de un solo ejecutable

Para un usuario final basta con descargar **ControlRed.exe**. El ZIP para Windows contiene únicamente ese ejecutable. Incluye Python, el panel, los siete idiomas y la base de fabricantes; no necesita las carpetas del código fuente.

Npcap se instala por separado una sola vez. Al usar el programa se crea una carpeta datos junto al ejecutable para guardar nombres, permisos, recuperación y registros. Conserva esa carpeta al actualizar si quieres mantener tu configuración. ControlRed-v4.1.exe es la misma aplicación con el número de versión en el nombre.

El código completo se distribuye por separado en el paquete para GitHub.

## Búsqueda manual y bloqueos continuos

Se realiza una búsqueda al abrir o cambiar de adaptador. Después, solo al pulsar **Actualizar red**. La observación del tráfico local y el mantenimiento de los bloqueos siguen activos; actualiza si falta un dispositivo. No responder a una búsqueda ya no cancela un bloqueo existente.

Puedes cerrar o suspender la pestaña. Mantén el PC y el ejecutable encendidos. **Desbloquear**, **Pausar lista y desbloquear todos** o **Salir** detienen el control correspondiente. Los errores de red siguen provocando una restauración y pausa.

La versión 4.1 también corrige el origen Ethernet de los mensajes de restauración para evitar que la red aprenda las MAC de otros equipos en el puerto del PC. Queda pendiente comprobar su efecto sobre la velocidad en la red real.

## Actualizar y abrir

1. En la versión anterior, pulsa **Salir** para restaurar las conexiones antes de cerrar.
2. Abre `ControlRed-v4.1.exe` con clic derecho y **Ejecutar como administrador**. La instalación actual de Npcap de este equipo exige ese permiso.
3. Mantén tu VPN activa y selecciona tu adaptador Ethernet o Wi-Fi físico.
4. En **Control de acceso**, cambia **Bloqueo manual** por **Lista blanca**. Los dispositivos detectados sin permiso recibirán bloqueo automáticamente. El router y este PC están siempre permitidos.
5. Pulsa **Permitir** junto a cada dispositivo que quieras autorizar, o usa **Añadir MAC permitida** para introducir una dirección y un nombre opcional. También puedes preparar estos permisos antes de activar la lista blanca.
6. Para comprobar el resultado en el teléfono, desactiva temporalmente sus datos móviles, mantén su VPN activa e intenta cargar una página nueva.
7. Usa **Pausar lista y desbloquear todos** o **Salir** para enviar la restauración.

`Demostracion.cmd` abre una red simulada para explorar el panel. La franja azul identifica esa modalidad.

## Idiomas

La barra superior permite elegir Español, English, Deutsch, Français, 简体中文, Português o Русский. La selección se guarda en el navegador. En la primera visita se usa un idioma compatible del navegador y, si no hay ninguno, inglés.

Se traducen el panel, los estados, los diálogos, los errores y la actividad. Los nombres personalizados, las MAC, las IP, los nombres reales de adaptadores y los fabricantes registrados conservan su texto original. Cambiar de idioma no cambia permisos ni detiene el control de acceso. Los catálogos están incluidos en el programa y funcionan sin internet.

[Documentación internacional y preparación para GitHub](README.md)

## Funciones de acceso

- La lista blanca bloquea por defecto los dispositivos detectados que no has autorizado. Los equipos nuevos observados entre escaneos se incorporan al siguiente ciclo de control.
- **Permisos guardados** permite consultar y retirar autorizaciones incluso cuando el equipo está desconectado. Puedes añadir una MAC antes de que aparezca en la red.
- El modo y los permisos se guardan en `datos/access.json`, separados por la MAC del router. Un cambio de IP mantiene el permiso. Cambiar a otra red carga su propia configuración.
- **Pausar lista y desbloquear todos** conserva los permisos y detiene los bloqueos hasta pulsar **Reanudar lista blanca**. Un error de transmisión también pausa la lista; cerrar la pestaña no la pausa. Volver a escanear no la reactiva.
- **Bloqueo manual** restaura los bloqueos de la lista blanca y permite controlar dispositivos individualmente. Los permisos guardados se conservan para cuando vuelvas a activar la lista.
- Al cerrar se restauran las conexiones. Al volver a abrir el programa se recupera el modo guardado y, si era lista blanca, se aplica de nuevo tras detectar la red. La pausa es temporal para la sesión actual.
- Se conserva el control por el adaptador físico con la VPN activa, los mensajes ARP bidireccionales, IPv6 dirigido a las direcciones observadas y los nombres personalizados de la versión anterior.

## Fabricantes

La columna **Fabricante** identifica al titular del bloque de la dirección MAC. Puede corresponder al fabricante del adaptador o del módulo de red. La búsqueda del panel incluye ese campo.

La base contiene 58.821 bloques de 24, 28 y 36 bits. Se consultan localmente, con preferencia por el bloque más específico. Una MAC administrada localmente aparece como **MAC privada / local**. Los equipos que no publican nombre se pueden identificar con **Renombrar**.

La base se obtuvo del archivo oficial de Wireshark el 17 de noviembre de 2026, que recopila los registros de fabricantes. Su cabecera original está incluida en `data/manuf.gz`.

[Base de fabricantes de Wireshark](https://www.wireshark.org/download/automated/data/manuf.gz)

## Alcance y comprobaciones pendientes

El panel indica **Bloqueo solicitado** porque enviar los mensajes de control no prueba que un equipo haya perdido internet. Una VPN necesita una conexión de transporte a su servidor. La efectividad depende de que los mensajes enviados actúen sobre la vía física usada por esa conexión.

IPv6 requiere descubrir las direcciones del equipo y el router IPv6. El panel indica si ha detectado este último. Los clientes que ignoran esos anuncios o los routers con protección ARP/NDP pueden conservar acceso. Para imponer el bloqueo completo de acceso a la red se necesita control en el router o en una pasarela que transporte todo el tráfico del dispositivo.

Los cambios de IP se siguen por MAC. Si un teléfono cambia su MAC privada, aparece como un dispositivo nuevo y necesita otro permiso en la lista blanca. La MAC es una identificación de red, no una autenticación contra suplantaciones. El control actúa sobre esta red local. Una conexión móvil independiente sigue disponible.

El bloqueo automático empieza cuando se detecta el dispositivo y funciona mientras el PC y el programa están activos. Esta aplicación no configura una lista de acceso en el router ni garantiza impedir la primera conexión de un equipo nuevo.

La pestaña del navegador puede cerrarse sin detener los bloqueos. Si el proceso termina abruptamente, queda un registro en `datos/recovery.json` para intentar recuperar la conexión al abrirlo de nuevo en la misma red.

La versión 4 incluye pruebas automatizadas de idiomas, integridad de catálogos, aislamiento de preferencias entre clientes, lista blanca, persistencia por red, cambios de IP, detección entre escaneos, pausa, restauración, validación de MAC, mensajes IPv4/IPv6 y autenticación del panel. Las pruebas automatizadas usan una red simulada.

## Código

Python 3.10 o posterior y su biblioteca estándar son suficientes para ejecutar `python app.py`. El ejecutable incluye Python. Npcap se instala por separado.

[Descarga oficial de Npcap](https://npcap.com/#download)

Las pruebas se ejecutan con `python -m unittest discover -s tests -v`. Los errores se registran en `datos/app.log`.
