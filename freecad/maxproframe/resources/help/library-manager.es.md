# Gestor de bibliotecas de perfiles

El gestor de bibliotecas de perfiles guarda los catálogos de perfiles que usás en tus estructuras: perfiles de acero, extrusiones de aluminio, madera o tus propias secciones dibujadas. Se abre con el botón **Gestionar Bibliotecas de Perfiles** de la barra de herramientas.

La ventana tiene tres zonas:

- **Bibliotecas disponibles** (arriba a la izquierda): todos los catálogos que podés usar.
- **Familias en la biblioteca** (abajo a la izquierda): las familias de la biblioteca seleccionada, como *Tubo Cuadrado Hueco* o *Perfil personalizado*.
- **Perfiles** (a la derecha): las medidas de la familia seleccionada, en una tabla o, para los perfiles personalizados, en tarjetas.

Apretá **F1** o hacé clic en **?** en cualquier momento para abrir esta guía en la sección de lo que estás haciendo.

## Bibliotecas

Cada biblioteca tiene un material y una densidad, que se usan para calcular el peso de los perfiles. La lista indica su tipo:

- Las bibliotecas **[Sistema]** vienen con MaxProFrame. Son de solo lectura: duplicá una para modificarla.
- Las bibliotecas **[Carpeta]** viven en una carpeta que elegís vos, junto con sus secciones. Copiá o sincronizá esa carpeta para usarla en otra computadora.
- Las bibliotecas **[Usuario]** son bibliotecas personales anteriores, guardadas en la carpeta de usuario de FreeCAD.

Los botones arriba de la lista son, en orden: **Nueva Biblioteca** (+), **Eliminar Biblioteca** (−), **Importar biblioteca**, **Duplicar Biblioteca** y **Exportar biblioteca**. Pasá el mouse sobre cualquier botón para ver qué hace. En una biblioteca en carpeta, − solo quita su registro: los archivos en disco se conservan.

## Crear una biblioteca

1. Hacé clic en **Nueva Biblioteca** (+).
2. Escribí un nombre y elegí el material y la densidad.
3. Revisá la carpeta de destino. Por defecto se crea una carpeta nueva con el nombre de la biblioteca dentro de tu carpeta de perfiles de usuario; **Elegí una carpeta…** selecciona otra carpeta vacía.
4. Hacé clic en **OK**. La biblioteca nueva queda seleccionada y lista para agregarle familias.

## Duplicar una biblioteca del sistema

Las bibliotecas del sistema no se pueden editar. Para partir de una de ellas:

1. Seleccioná la biblioteca y hacé clic en **Duplicar Biblioteca**.
2. Escribí el nombre nuevo, el material y la densidad. Activá **Recalcular pesos teóricos para el nuevo material** para actualizar los pesos con la densidad nueva.
3. Elegí la carpeta de destino y hacé clic en **OK**.

La copia es una biblioteca en carpeta que podés editar, guardar y compartir.

## Compartir una biblioteca

- **Exportar biblioteca** guarda la biblioteca en carpeta seleccionada, con sus secciones, en un archivo ZIP. Primero guardá o cancelá los cambios pendientes; las bibliotecas del sistema hay que duplicarlas antes de exportarlas.
- **Importar biblioteca → Importar ZIP…** agrega una biblioteca desde un archivo ZIP, en su propia carpeta.
- **Importar biblioteca → Registrar biblioteca en carpeta** usa una carpeta de biblioteca existente en su lugar, por ejemplo una carpeta compartida o sincronizada. Seleccioná la carpeta que contiene `library.json`.

Nunca se sobrescriben bibliotecas ni archivos existentes: si el nombre o la carpeta ya están en uso, se rechaza.

## Familias

Una familia agrupa perfiles de la misma forma, como *IPE*, *Tubo Cuadrado Hueco* o *Perfil personalizado*.

- **Agregar Familia** (+) abre una lista de formas con una vista previa. Activá **Con redondeos** para esquinas redondeadas cuando la forma lo permite.
- **Eliminar Familia** (−) quita de la biblioteca la familia seleccionada y sus perfiles.
- **Norma / Ref** guarda la norma o la referencia de catálogo de la familia, como *EN 10219*.

Las familias solo se pueden cambiar en bibliotecas editables.

## Perfiles y medidas

En las formas estándar, cada fila de la tabla es una medida:

- **Agregar Medida** (+) agrega una fila; escribí su código y sus dimensiones en milímetros.
- **Quitar Medida** (−) pide confirmación y quita la fila seleccionada.
- El peso en kg/m se calcula a partir de las dimensiones y la densidad de la biblioteca.
- **Buscar en esta familia…** filtra las filas por código o descripción, sin distinguir mayúsculas ni acentos. Borrá la búsqueda para ver de nuevo todos los perfiles; buscar nunca borra nada.

## Perfiles personalizados

La familia *Perfil personalizado* guarda cualquier sección cerrada que dibujes, y la muestra en tarjetas con la sección, su código y su peso.

- **Capturar sección**: dibujá la sección en un croquis de Sketcher con un contorno exterior cerrado y los huecos cerrados que necesites, seleccioná el croquis y hacé clic en el botón.
- **Importar DXF**: elegí un archivo DXF con polilíneas cerradas, confirmá sus unidades, revisá la sección y hacé clic en **Agregar como personalizado** con un código único.
- El lápiz de una tarjeta abre **Editar propiedades** para cambiar su código, descripción y peso. **Editar sección** abre la sección en Sketcher; hacé clic en **OK** en la ventana **Editar perfil** para conservar la geometría nueva.

El peso de las secciones capturadas e importadas se calcula a partir de su área y la densidad de la biblioteca.

## Guardar los cambios

Los cambios quedan pendientes hasta que hacés clic en **Guardar Cambios**, que se habilita solo cuando hay algo para guardar. Si cerrás la ventana o cambiás de biblioteca con cambios pendientes, podés elegir **Guardar**, **Descartar** o **Cancelar**.

## Usar los perfiles en un modelo

Abrí **Crear perfiles**, elegí la biblioteca en la lista de materiales y después la familia y la medida. Seleccioná las aristas del recorrido en la vista 3D y confirmá. Las secciones personalizadas se copian en tu documento, así que el modelo sigue funcionando sin la biblioteca.
