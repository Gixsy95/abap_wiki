*&---------------------------------------------------------------------*
*& Report ZDEMO_STOCK_REPORT
*&---------------------------------------------------------------------*
*& SYNTHETIC demo (abap_wiki demo-system) - NOT code from a real system.
*& Lists the stock of the demo table ZDEMO_STOCK below a threshold and
*& enriches each row through the function module ZDEMO_FG_GET_STOCK.
*& Output: ALV grid. Errors raised through message class ZDEMO_MSG.
*&---------------------------------------------------------------------*
REPORT zdemo_stock_report.

INCLUDE zdemo_stock_report_top.
INCLUDE zdemo_stock_report_f01.

*----------------------------------------------------------------------*
* Selection screen
*----------------------------------------------------------------------*
SELECTION-SCREEN BEGIN OF BLOCK b1 WITH FRAME TITLE TEXT-001.
SELECT-OPTIONS: s_matnr FOR gs_stock-matnr,
                s_werks FOR gs_stock-werks OBLIGATORY.
PARAMETERS:     p_minqty TYPE zdemo_quantity DEFAULT 10,
                p_detail AS CHECKBOX DEFAULT 'X'.
SELECTION-SCREEN END OF BLOCK b1.

*----------------------------------------------------------------------*
* Main
*----------------------------------------------------------------------*
START-OF-SELECTION.
  PERFORM extract_stock.
  IF p_detail = 'X'.
    PERFORM enrich_details.
  ENDIF.

END-OF-SELECTION.
  IF gt_stock IS INITIAL.
    MESSAGE s001(zdemo_msg).
    RETURN.
  ENDIF.
  PERFORM display_alv.
