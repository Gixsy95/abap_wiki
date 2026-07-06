*&---------------------------------------------------------------------*
*& Include ZDEMO_STOCK_REPORT_F01 - forms of ZDEMO_STOCK_REPORT
*&---------------------------------------------------------------------*
*& SYNTHETIC demo (abap_wiki demo-system) - NOT code from a real system.
*&---------------------------------------------------------------------*

*&---------------------------------------------------------------------*
*& Form EXTRACT_STOCK
*&---------------------------------------------------------------------*
*& Reads ZDEMO_STOCK below the requested threshold.
*&---------------------------------------------------------------------*
FORM extract_stock.
  SELECT matnr, werks, lgort, quantity
    FROM zdemo_stock
    WHERE matnr IN @s_matnr
      AND werks IN @s_werks
      AND quantity < @p_minqty
    INTO CORRESPONDING FIELDS OF TABLE @gt_stock.
  gv_lines = lines( gt_stock ).
ENDFORM.

*&---------------------------------------------------------------------*
*& Form ENRICH_DETAILS
*&---------------------------------------------------------------------*
*& Deliberate demo finding: a CALL FUNCTION with a SELECT inside a LOOP
*& (N+1 access) for the L1 analysis to flag as a bug candidate.
*&---------------------------------------------------------------------*
FORM enrich_details.
  LOOP AT gt_stock ASSIGNING FIELD-SYMBOL(<ls_stock>).
    CALL FUNCTION 'ZDEMO_FG_GET_STOCK'
      EXPORTING
        iv_matnr    = <ls_stock>-matnr
        iv_werks    = <ls_stock>-werks
      IMPORTING
        ev_quantity = <ls_stock>-quantity.
    IF sy-subrc <> 0.
      MESSAGE e002(zdemo_msg) WITH <ls_stock>-matnr.
    ENDIF.
  ENDLOOP.
ENDFORM.

*&---------------------------------------------------------------------*
*& Form DISPLAY_ALV
*&---------------------------------------------------------------------*
FORM display_alv.
  DATA lo_alv TYPE REF TO cl_salv_table.
  TRY.
      cl_salv_table=>factory( IMPORTING r_salv_table = lo_alv
                              CHANGING  t_table      = gt_stock ).
      lo_alv->display( ).
    CATCH cx_salv_msg.
      MESSAGE e003(zdemo_msg).
  ENDTRY.
ENDFORM.
