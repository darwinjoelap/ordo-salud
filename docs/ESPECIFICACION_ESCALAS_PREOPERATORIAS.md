# Escalas de Evaluación Preoperatoria

Las escalas se presentan dentro de la valoración habitual. Solo se conserva el resultado que el profesional calculó,
revisó y confirmó al guardar. El servidor comprueba que el resultado mostrado corresponde a los factores, el usuario,
la consulta y la versión de valoración. La edición de una consulta cerrada utiliza la enmienda de la valoración.
Los PDF previos mantienen sus bytes originales. ASA-PS y METS manuales conservan sus campos y procedencia.

Para interpretar cada resultado se debe confirmar la población descrita en la interfaz. Los datos discordantes,
desconocidos o inválidos bloquean el puntaje. Cero identifica una contribución ausente tras revisar el factor.
Los índices describen un desenlace o una capacidad funcional. El profesional redacta las conclusiones y las indicaciones.

| Escala | Versión y ámbito | Estado y reglas documentadas |
|---|---|---|
| Goldman | [Goldman 1977](https://pubmed.ncbi.nlm.nih.gov/904659/), mayores de 40 años con cirugía mayor no cardíaca | Índice histórico. Edad >70 años y ectopia >5/min. Cantidades exactamente iguales a los límites no puntúan. S3 o distensión yugular y el compuesto de estado general aportan una sola contribución cada uno. La fecha exacta a seis meses del infarto queda pendiente de adjudicación. [Tabla de factores reproducida](https://www.sciencedirect.com/science/article/pii/S0950350198800585/pdf). |
| Detsky | [Detsky 1986](https://pubmed.ncbi.nlm.nih.gov/3778043/), consulta preoperatoria adulta no cardíaca | Índice histórico. La clase CCS III o IV puede sumar con angina inestable dentro de tres meses. Las ramas temporales de infarto y edema son excluyentes por evento. Bloqueados los casos de 70 años exactos, infarto a seis meses exactos y edema a siete días exactos. El texto original y una tabla posterior discrepan sobre la edad. El nomograma requiere calibración local. [Casos publicados](https://www.academia.edu/126723151/Cardiac_Assessment_for_Patients_Undergoing_Noncardiac_Surgery_A_Multifactorial_Clinical_Risk_Index), [clases históricas](https://www.ucl.ac.uk/anaesthesia/sites/anaesthesia/files/reilly-1999.pdf). |
| Caprini | [RAM 2013, guía y licencia de Cronin 2019](https://capriniriskscore.org/wp-content/uploads/2025/02/Completion-of-the-Updated-Caprini-Risk-Assessment-Model-2013-Version.pdf), adultos quirúrgicos | Motor comprobado con casos sintéticos. La ficha clínica muestra la restricción. La guía pública usa CC BY-NC 4.0. Quedan pendientes los derechos comerciales de reproducción del material y la adjudicación de 45 min exactos, VIH y posibles solapamientos de trauma y fractura. La duración incluye anestesia. Se excluyen los puntos de duración de la misma artroplastia total. Se ingresan episodios venosos distintos. TVP y embolia pulmonar simultáneas forman un solo episodio. El corte ≥10 de artroplastia se estudió usando el puntaje previo al alta y no se generaliza al resultado preoperatorio. [Krauss et al.](https://pubmed.ncbi.nlm.nih.gov/30939898/). |
| ARISCAT | [Canet 2010, tablas 6 y 7](https://www.hospitaldelmar.cat/media/upload_web/pdf/article_Anesthesiology_editora_46_3389_1.pdf), adultos hospitalizados dentro del ámbito descrito en la interfaz | Hb ≤10 g/dL puntúa 11, de acuerdo con la tabla de puntuación y la validación externa. Registrar SpO₂ entera en aire ambiente y decúbito supino. Duración quirúrgica prevista en minutos. Exactamente 120 min puntúa 0 y exactamente 180 min puntúa 16. Clases <26, 26–44 y ≥45. [Validación externa de Mazo](https://doi.org/10.1097/ALN.0000000000000334). |
| RCRI | [Lee 1999, tablas 1–3](https://escholarship.org/content/qt845640mb/qt845640mb.pdf), edad ≥50 con cirugía mayor no cardíaca no urgente, estable y estancia esperada ≥2 días | Creatinina sérica preoperatoria >2,0 mg/dL. No se redondea antes de comparar. Las tasas se atribuyen a la cohorte original de validación y al desenlace mayor intrahospitalario. La revascularización aislada no basta para el factor isquémico. |
| DASI | [Hlatky 1989](https://pubmed.ncbi.nlm.nih.gov/2782256/), capacidad funcional autorreportada | Motor comprobado con vectores de doce respuestas explícitas, sin reproducir el cuestionario. Guarda precisión decimal y calcula VO₂ pico estimado y METS estimados con la ecuación original. El corte perioperatorio ≤34 se aplica al puntaje DASI en el contexto estudiado. Pendientes autorización electrónica comercial y versión española autorizada. [Ficha DASI](https://eprovide.mapi-trust.org/instruments/duke-activity-status-index), [cohorte perioperatoria](https://discovery.ucl.ac.uk/id/eprint/10095756/1/1-s2.0-S0007091219309298-main.pdf). |

Las pruebas de referencia viven en `tests/test_reglas_preoperatorias.py`. Incluyen los dos ejemplos publicados de
Detsky y los umbrales exactos de ARISCAT y Lee. `tests/test_escalas_preoperatorias.py` verifica el guardado, el rechazo de
confirmaciones manipuladas y de otro consultorio, la separación de escalas restringidas, las enmiendas y el PDF.

La valoración conserva los insumos, el desglose, la fuente, el puntaje, la versión y el autor. Si el carácter de la
cirugía cambia y contradice los factores confirmados o excluye la población, la historia muestra el motivo de revisión.
El informe de la versión actual omite ese resultado hasta que la valoración sea coherente.
