# Fundación - Conformidad de rendiciones

Conformidad **posterior** del Gerente sobre los Anexos I (`fund_expense_report`) ya aprobados.
Los Anexos tienen sus dos firmas y pueden estar pagados. El Gerente da su conformidad sobre el
lote del período, de una sola vez, y observa los Anexos que no le cierran.

## Cómo funciona

1. **Se arma la conformidad** (*Gastos → Conformidades*), con un período (*Desde* / *Hasta*).
   - **Agregar aprobados pendientes** suma todos los Anexos aprobados hasta la fecha *Hasta* que
     no estén en otra conformidad, aunque sean de antes del período: no queda ninguno afuera.
   - Administración puede quitar Anexos o sumar uno a mano antes de enviarla.
   - Cada Anexo está en una sola conformidad.
2. **Se envía al Gerente** con *Solicitar validación*. Aparece en **Mis aprobaciones** y en su
   resumen diario como un único documento. Desde ese momento no se pueden sumar ni quitar Anexos.
3. **El Gerente revisa**: ve el listado, los totales por área y por fondo, y puede abrir cada
   Anexo (solo lectura, sin permisos de Gastos).
   - **Observar** un Anexo pide el motivo. El Anexo queda *Observado*, con nota interna en su
     historial y una **actividad** para el responsable de la conformidad.
   - **Aprobar** da la conformidad del lote entero, aunque haya Anexos observados. Cada Anexo
     queda *Conforme* u *Observado*, con nota interna.
   - **Rechazar** pide el motivo y devuelve el lote a Administración, que reinicia la validación
     para corregirlo y volver a enviarlo.
4. **PDF** (*Imprimir → Conformidad de rendiciones*): listado, totales por área y por fondo,
   observaciones y quién dio la conformidad y cuándo.

La conformidad no bloquea ni deshace nada: los Anexos se pagan con sus dos firmas, como siempre.

### El Anexo después de entrar en una conformidad

- En el Anexo se ven la conformidad y su estado (*Pendiente*, *Conforme*, *Observado*), con la
  observación. En la lista de rendiciones hay filtros **Aprobados sin conformidad** y
  **Observados por el Gerente**.
- Si un Anexo aprobado se rechaza o vuelve a borrador mientras su conformidad está en armado,
  sale de ella. Si la conformidad ya se envió o ya se dio, no se puede: el Gerente estaría
  firmando algo que cambió.

## Configuración

1. **Grupo:** asignar *Gastos → Conformidad de rendiciones (Gerente)* al Gerente. Ve todas las
   conformidades y sus Anexos.
2. **Definición de aprobación:** se instala *Conformidad del Gerente*, por grupo, con aviso al
   crearse. Se puede cambiar por un usuario o sumar niveles.
3. **Frecuencia** (*Gastos → Configuración → Ajustes → Conformidad de rendiciones*), por compañía:
   - **Manual** (por defecto): Administración arma cada conformidad.
   - **Semanal** o **Mensual**: al terminar cada semana (lunes a domingo) o mes se arma sola con
     todos los Anexos aprobados pendientes y se envía al Gerente. Si no hay ninguno, no se arma.
     El *Responsable de las conformidades* recibe las observaciones.
   - La primera automática incluye **todos** los aprobados sin conformidad, también los
     anteriores. Para empezar desde una fecha, conviene armar antes una manual con los viejos.
