*&---------------------------------------------------------------------*
*& Report ZEXAMPLE_STOCK_ALLOC
*&---------------------------------------------------------------------*
*& SYNTHETIC example (abap_wiki template) - NOT code from a real system.
*& Summarises the stock by material/plant and proposes a reallocation toward
*& the plants below minimum stock. Output: ALV, file on AL11, notification email.
*&---------------------------------------------------------------------*
REPORT zexample_stock_alloc.

TYPES: BEGIN OF ty_stock,
         matnr TYPE mara-matnr,
         werks TYPE marc-werks,
         lgort TYPE mard-lgort,
         labst TYPE mard-labst,
         meins TYPE mara-meins,
         minbe TYPE marc-minbe,
         deficit TYPE mard-labst,
       END OF ty_stock,
       tt_stock TYPE STANDARD TABLE OF ty_stock WITH DEFAULT KEY.

DATA: gt_stock   TYPE tt_stock,
      gt_alloc   TYPE tt_stock,
      gv_file    TYPE string,
      gv_lines   TYPE i.

CONSTANTS: gc_path TYPE string VALUE '/usr/sap/tmp/stock_alloc.csv'.

*----------------------------------------------------------------------*
* Selection screen
*----------------------------------------------------------------------*
SELECTION-SCREEN BEGIN OF BLOCK b1 WITH FRAME TITLE TEXT-001.
SELECT-OPTIONS: s_matnr FOR gt_stock-matnr,
                s_werks FOR gt_stock-werks OBLIGATORY.
PARAMETERS:     p_lgort TYPE mard-lgort,
                p_below AS CHECKBOX DEFAULT 'X',
                p_mail  TYPE ad_smtpadr.
SELECTION-SCREEN END OF BLOCK b1.

*----------------------------------------------------------------------*
* Main
*----------------------------------------------------------------------*
START-OF-SELECTION.
  PERFORM extract_stock.
  PERFORM compute_allocation.
  PERFORM write_file.
  PERFORM send_notification.

END-OF-SELECTION.
  PERFORM display_alv.

*&---------------------------------------------------------------------*
*& Form extract_stock
*&---------------------------------------------------------------------*
FORM extract_stock.
  SELECT m~matnr c~werks d~lgort d~labst a~meins c~minbe
    FROM mard AS d
    INNER JOIN marc AS c ON c~matnr = d~matnr AND c~werks = d~werks
    INNER JOIN mara AS a ON a~matnr = d~matnr
    INNER JOIN mara AS m ON m~matnr = d~matnr
    INTO CORRESPONDING FIELDS OF TABLE gt_stock
    WHERE d~matnr IN s_matnr
      AND d~werks IN s_werks
      AND ( d~lgort = p_lgort OR p_lgort = space ).
  IF sy-subrc <> 0.
    MESSAGE i001(zexample) WITH 'No stock for the selected criteria'.
  ENDIF.
  gv_lines = lines( gt_stock ).
ENDFORM.

*&---------------------------------------------------------------------*
*& Form compute_allocation
*&---------------------------------------------------------------------*
FORM compute_allocation.
  DATA lv_deficit TYPE mard-labst.
  LOOP AT gt_stock ASSIGNING FIELD-SYMBOL(<fs>).
    lv_deficit = <fs>-minbe - <fs>-labst.
    IF lv_deficit > 0.
      <fs>-deficit = lv_deficit.
      IF p_below = abap_true.
        APPEND <fs> TO gt_alloc.
      ENDIF.
    ENDIF.
  ENDLOOP.
  SORT gt_alloc BY deficit DESCENDING.
ENDFORM.

*&---------------------------------------------------------------------*
*& Form write_file
*&---------------------------------------------------------------------*
FORM write_file.
  DATA lv_rec TYPE string.
  gv_file = gc_path.
  OPEN DATASET gv_file FOR OUTPUT IN TEXT MODE ENCODING UTF-8.
  IF sy-subrc <> 0.
    MESSAGE e002(zexample) WITH gv_file.
    RETURN.
  ENDIF.
  LOOP AT gt_alloc INTO DATA(ls_alloc).
    CONCATENATE ls_alloc-matnr ls_alloc-werks ls_alloc-lgort
                ls_alloc-labst ls_alloc-minbe ls_alloc-deficit
           INTO lv_rec SEPARATED BY ';'.
    TRANSFER lv_rec TO gv_file.
  ENDLOOP.
  CLOSE DATASET gv_file.
ENDFORM.

*&---------------------------------------------------------------------*
*& Form send_notification
*&---------------------------------------------------------------------*
FORM send_notification.
  IF p_mail IS INITIAL OR gt_alloc IS INITIAL.
    RETURN.
  ENDIF.
  DATA(lo_send) = cl_bcs=>create_persistent( ).
  DATA(lo_doc) = cl_document_bcs=>create_document(
                   i_type    = 'RAW'
                   i_text    = VALUE bcsy_text( ( line = |Materials below stock: { lines( gt_alloc ) }| ) )
                   i_subject = 'Stock reallocation' ).
  lo_send->set_document( lo_doc ).
  lo_send->add_recipient( cl_cam_address_bcs=>create_internet_address( p_mail ) ).
  lo_send->send( ).
  COMMIT WORK.
ENDFORM.

*&---------------------------------------------------------------------*
*& Form display_alv
*&---------------------------------------------------------------------*
FORM display_alv.
  DATA lo_alv TYPE REF TO cl_salv_table.
  TRY.
      cl_salv_table=>factory( IMPORTING r_salv_table = lo_alv
                              CHANGING  t_table      = gt_alloc ).
      lo_alv->get_functions( )->set_all( abap_true ).
      lo_alv->display( ).
    CATCH cx_salv_msg INTO DATA(lx).
      MESSAGE lx->get_text( ) TYPE 'I'.
  ENDTRY.
ENDFORM.
