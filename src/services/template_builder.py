import logging
from src.core.google_client import google_manager

logger = logging.getLogger(__name__)

class TemplateBuilderService:
    def __init__(self):
        self.docs_service = google_manager.docs_service

    def inject_fase1_table(self, document_id, tab_id, abusos_data):
        """
        Crea la tabla de Fase 1 en la Pestaña 1 y la rellena usando manipulación de índices (AST).
        Incluye inyección de texto simultánea con formato tipográfico y estético avanzado.
        """
        try:
            logger.info(f"Creando tabla de Fase 1 ({len(abusos_data)} filas) en el documento...")
            
            # 1. Crear la tabla vacía al final de la pestaña
            requests = [{
                'insertTable': {
                    'rows': len(abusos_data) + 1,
                    'columns': 4,
                    'endOfSegmentLocation': {'tabId': tab_id}
                }
            }]
            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': requests}).execute()

            # 2. Obtener la estructura fresca del documento
            doc = self.docs_service.documents().get(documentId=document_id, includeTabsContent=True).execute()
            
            tab_content = None
            for t in doc.get('tabs', []):
                if t.get('tabProperties', {}).get('tabId') == tab_id:
                    tab_content = t['documentTab']['body']['content']
                    break
                    
            if not tab_content:
                raise ValueError("No se encontró el contenido de la pestaña 1.")

            # Buscar la tabla que acabamos de insertar
            table_element = None
            table_start_index = None
            for el in reversed(tab_content):
                if 'table' in el:
                    table_element = el['table']
                    table_start_index = el.get('startIndex')
                    break

            if not table_element or table_start_index is None:
                raise ValueError("No se encontró la tabla recién creada en el AST.")

            # 3. Recolectar índices de celdas para inyectar texto y formato
            inserts = []
            
            # Encabezados
            headers = ["Fragmento del Testimonio", "Evento / Patrón", "Clasificación del Abuso", "Página"]
            for col_idx, header_text in enumerate(headers):
                cell = table_element['tableRows'][0]['tableCells'][col_idx]
                idx = cell['content'][0]['startIndex']
                inserts.append({'idx': idx, 'text': header_text, 'type': 'header'})

            # Filas de datos
            for row_idx, abuso in enumerate(abusos_data):
                row = table_element['tableRows'][row_idx + 1]
                inserts.append({'idx': row['tableCells'][0]['content'][0]['startIndex'], 'text': abuso.get('fragmento', 'N/A'), 'type': 'data'})
                inserts.append({'idx': row['tableCells'][1]['content'][0]['startIndex'], 'text': abuso.get('evento', 'N/A'), 'type': 'data'})
                inserts.append({'idx': row['tableCells'][2]['content'][0]['startIndex'], 'text': abuso.get('clasificacion', 'N/A'), 'type': 'data_center'})
                inserts.append({'idx': row['tableCells'][3]['content'][0]['startIndex'], 'text': abuso.get('pagina', 'N/A'), 'type': 'data_center'})

            # CRÍTICO: Ordenar de MAYOR a MENOR para evitar el desplazamiento de índices
            inserts.sort(key=lambda x: x['idx'], reverse=True)

            text_requests = []
            for item in inserts:
                idx = item['idx']
                text = str(item['text'])
                req_type = item['type']
                
                if text:
                    # Inserción de texto
                    text_requests.append({
                        'insertText': {
                            'location': {'tabId': tab_id, 'index': idx},
                            'text': text
                        }
                    })
                    
                    # Formato tipográfico dinámico
                    if req_type == 'header':
                        text_requests.append({
                            'updateTextStyle': {
                                'range': {'tabId': tab_id, 'startIndex': idx, 'endIndex': idx + len(text)},
                                'textStyle': {
                                    'bold': True, 
                                    'fontSize': {'magnitude': 11, 'unit': 'PT'},
                                    'foregroundColor': {'color': {'rgbColor': {'red': 1.0, 'green': 1.0, 'blue': 1.0}}} # Blanco
                                },
                                'fields': 'bold,fontSize,foregroundColor'
                            }
                        })
                        text_requests.append({
                            'updateParagraphStyle': {
                                'range': {'tabId': tab_id, 'startIndex': idx, 'endIndex': idx + len(text)},
                                'paragraphStyle': {'alignment': 'CENTER'},
                                'fields': 'alignment'
                            }
                        })
                    elif req_type == 'data_center':
                        text_requests.append({
                            'updateParagraphStyle': {
                                'range': {'tabId': tab_id, 'startIndex': idx, 'endIndex': idx + len(text)},
                                'paragraphStyle': {'alignment': 'CENTER'},
                                'fields': 'alignment'
                            }
                        })

            if text_requests:
                self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': text_requests}).execute()

            # 4. APLICAR ESTRUCTURA ESTÉTICA Y CORPORATIVA
            style_requests = [
                # Configuración de anchos
                {
                    'updateTableColumnProperties': {
                        'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                        'columnIndices': [0], 
                        'tableColumnProperties': {'widthType': 'FIXED_WIDTH', 'width': {'magnitude': 240, 'unit': 'PT'}},
                        'fields': 'width,widthType'
                    }
                },
                {
                    'updateTableColumnProperties': {
                        'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                        'columnIndices': [1, 2], 
                        'tableColumnProperties': {'widthType': 'FIXED_WIDTH', 'width': {'magnitude': 110, 'unit': 'PT'}},
                        'fields': 'width,widthType'
                    }
                },
                {
                    'updateTableColumnProperties': {
                        'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                        'columnIndices': [3], 
                        'tableColumnProperties': {'widthType': 'FIXED_WIDTH', 'width': {'magnitude': 50, 'unit': 'PT'}},
                        'fields': 'width,widthType'
                    }
                },
                # Padding y alineación vertical global (Aplica a toda la tabla)
                {
                    'updateTableCellStyle': {
                        'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                        'tableCellStyle': {
                            'contentAlignment': 'MIDDLE',
                            'paddingTop': {'magnitude': 5, 'unit': 'PT'},
                            'paddingBottom': {'magnitude': 5, 'unit': 'PT'},
                            'paddingLeft': {'magnitude': 6, 'unit': 'PT'},
                            'paddingRight': {'magnitude': 6, 'unit': 'PT'}
                        },
                        'fields': 'contentAlignment,paddingTop,paddingBottom,paddingLeft,paddingRight'
                    }
                },
                # Fondo oscuro para el encabezado (Aplica a rango específico: fila 0)
                {
                    'updateTableCellStyle': {
                        'tableRange': {
                            'tableCellLocation': {
                                'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                                'rowIndex': 0,
                                'columnIndex': 0
                            },
                            'rowSpan': 1,
                            'columnSpan': 4
                        },
                        'tableCellStyle': {
                            'backgroundColor': {
                                'color': {'rgbColor': {'red': 0.25, 'green': 0.35, 'blue': 0.45}} # Azul corporativo oscuro
                            }
                        },
                        'fields': 'backgroundColor'
                    }
                }
            ]

            # Zebra Striping: Colores alternados para lectura fluida
            for r_idx in range(1, len(abusos_data) + 1):
                if r_idx % 2 == 0:
                    style_requests.append({
                        'updateTableCellStyle': {
                            'tableRange': {
                                'tableCellLocation': {
                                    'tableStartLocation': {'index': table_start_index, 'tabId': tab_id},
                                    'rowIndex': r_idx,
                                    'columnIndex': 0
                                },
                                'rowSpan': 1,
                                'columnSpan': 4
                            },
                            'tableCellStyle': {
                                'backgroundColor': {
                                    'color': {'rgbColor': {'red': 0.96, 'green': 0.96, 'blue': 0.96}} # Gris claro
                                }
                            },
                            'fields': 'backgroundColor'
                        }
                    })

            self.docs_service.documents().batchUpdate(documentId=document_id, body={'requests': style_requests}).execute()
            logger.info("[✓] Estética profesional, colores y tipografía aplicada a la tabla de Fase 1.")

        except Exception as e:
            logger.error(f"Error inyectando tabla Fase 1: {e}")
            raise

    def fill_fase2_template(self, document_id, extracted_data):
        """
        Busca y reemplaza todas las etiquetas en el documento completo.
        (El contenido de este método se mantiene idéntico a la versión funcional).
        """
        try:
            logger.info("Reemplazando etiquetas de la Fase 2 (Estrategia Agresiva)...")
            
            def get_val(key):
                return str(extracted_data.get(key, "N/A"))

            base_map = {
                "cl_nombre": get_val("cl_nombre"),
                "abuser_nombre": get_val("abuser_nombre"),
                "cl_dob": get_val("cl_dob"),
                "abuser_dob": get_val("abuser_dob"),
                "cl_pob": get_val("cl_pob"),
                "abuser_pob": get_val("abuser_pob"),
                "cl_altura": get_val("cl_altura"),
                "abuser_altura": get_val("abuser_altura"),
                "cl_peso": get_val("cl_peso"),
                "abuser_peso": get_val("abuser_peso"),
                "estado_civil": get_val("estado_civil"),
                "estatus_legal": get_val("estatus_legal"),
                "cl_cargos": get_val("cl_cargos"),
                "abuser_cargos": get_val("abuser_cargos"),
                "hijos_comun": get_val("hijos_comun"),
                "viven_juntos": get_val("viven_juntos"),
                "conductas_abusivas_dcl": get_val("conductas_abusivas_dcl"),
                "evidencia_fisico": get_val("evidencia_fisico"),
                "ausencia_fisico": get_val("ausencia_fisico"),
                "evidencia_psico": get_val("evidencia_psico"),
                "ausencia_psico": get_val("ausencia_psico"),
                "evidencia_financiero": get_val("evidencia_financiero"),
                "ausencia_financiero": get_val("ausencia_financiero"),
                "evidencia_legal": get_val("evidencia_legal"),
                "ausencia_legal": get_val("ausencia_legal"),
                "uscis_aislamiento_ej": get_val("uscis_aislamiento_ej"),
                "uscis_aislamiento_cons": get_val("uscis_aislamiento_cons"),
                "uscis_humillacion_ej": get_val("uscis_humillacion_ej"),
                "uscis_humillacion_cons": get_val("uscis_humillacion_cons"),
                "uscis_degradacion_ej": get_val("uscis_degradacion_ej"),
                "uscis_degradacion_cons": get_val("uscis_degradacion_cons"),
                "uscis_economico_ej": get_val("uscis_economico_ej"),
                "uscis_economico_cons": get_val("uscis_economico_cons"),
                "uscis_coercion_ej": get_val("uscis_coercion_ej"),
                "uscis_coercion_cons": get_val("uscis_coercion_cons"),
                "uscis_amenazas_ej": get_val("uscis_amenazas_ej"),
                "uscis_amenazas_cons": get_val("uscis_amenazas_cons"),
                "uscis_miedo_ej": get_val("uscis_miedo_ej"),
                "uscis_miedo_cons": get_val("uscis_miedo_cons"),
                "uscis_control_ej": get_val("uscis_control_ej"),
                "uscis_control_cons": get_val("uscis_control_cons"),
                "uscis_negacion_ej": get_val("uscis_negacion_ej"),
                "uscis_negacion_cons": get_val("uscis_negacion_cons"),
                "uscis_deportacion_ej": get_val("uscis_deportacion_ej"),
                "uscis_deportacion_cons": get_val("uscis_deportacion_cons"),
                "uscis_hijos_ej": get_val("uscis_hijos_ej"),
                "uscis_hijos_cons": get_val("uscis_hijos_cons"),
                "uscis_detencion_ej": get_val("uscis_detencion_ej"),
                "uscis_detencion_cons": get_val("uscis_detencion_cons"),
                "uscis_psicosexual_ej": get_val("uscis_psicosexual_ej"),
                "uscis_psicosexual_cons": get_val("uscis_psicosexual_cons"),
                "uscis_patron_ej": get_val("uscis_patron_ej"),
                "uscis_patron_cons": get_val("uscis_patron_cons"),
                "uscis_terceros_ej": get_val("uscis_terceros_ej"),
                "uscis_terceros_cons": get_val("uscis_terceros_cons"),
                "uscis_testigo_hijo_ej": get_val("uscis_testigo_hijo_ej"),
                "uscis_testigo_hijo_cons": get_val("uscis_testigo_hijo_cons"),
            }

            requests = []
            
            impactos = extracted_data.get("tabla_impactos", [])
            base_map["imp_ano_base"] = "\n\n".join([str(i.get("ano", "")) for i in impactos]) or "N/A"
            base_map["imp_accion_base"] = "\n\n".join([str(i.get("accion", "")) for i in impactos]) or "N/A"
            base_map["imp_afecta_base"] = "\n\n".join([str(i.get("afecta", "")) for i in impactos]) or "N/A"
            base_map["imp_impacto_base"] = "\n\n".join([str(i.get("impacto", "")) for i in impactos]) or "N/A"

            financieros = extracted_data.get("tabla_financieros", [])
            base_map["fin_desc_base"] = "\n\n".join([str(f.get("descripcion", "")) for f in financieros]) or "N/A"
            base_map["fin_fecha_base"] = "\n\n".join([str(f.get("fecha", "")) for f in financieros]) or "N/A"
            base_map["fin_fecha_b"] = base_map["fin_fecha_base"] 
            base_map["fin_monto_base"] = "\n\n".join([str(f.get("monto", "")) for f in financieros]) or "N/A"
            base_map["fin_cons_base"] = "\n\n".join([str(f.get("consecuencia", "")) for f in financieros]) or "N/A"

            for key, value in base_map.items():
                tag_underscore = f"{{{{{key}}}}}"
                tag_space = f"{{{{{key.replace('_', ' ')}}}}}"
                
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': tag_underscore, 'matchCase': False}, 
                        'replaceText': str(value)
                    }
                })
                if tag_underscore != tag_space:
                    requests.append({
                        'replaceAllText': {
                            'containsText': {'text': tag_space, 'matchCase': False}, 
                            'replaceText': str(value)
                        }
                    })
            
            excepciones = [
                ("ase}}", ""),
                ("{{uscis detencion ej", base_map["uscis_detencion_ej"]),
                ("{{uscis patron ej }", base_map["uscis_patron_ej"]),
                ("{{uscis terceros ejl", base_map["uscis_terceros_ej"]),
                ("{{uscis testigo hijo ej }", base_map["uscis_testigo_hijo_ej"])
            ]
            for error_tag, correct_val in excepciones:
                requests.append({
                    'replaceAllText': {
                        'containsText': {'text': error_tag, 'matchCase': False},
                        'replaceText': str(correct_val)
                    }
                })

            if requests:
                self.docs_service.documents().batchUpdate(
                    documentId=document_id, 
                    body={'requests': requests}
                ).execute()
                logger.info("[✓] Todas las etiquetas han sido reemplazadas con éxito (Estrategia agresiva).")

        except Exception as e:
            logger.error(f"Error reemplazando etiquetas en Template 3.2: {e}")
            raise

template_builder = TemplateBuilderService()