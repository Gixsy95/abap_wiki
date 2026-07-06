* SYNTHETIC demo (abap_wiki demo-system) - NOT code from a real system.
FUNCTION zdemo_fg_get_stock.
*"----------------------------------------------------------------------
*"*"Local Interface:
*"  IMPORTING
*"     VALUE(IV_MATNR) TYPE  ZDEMO_STOCK-MATNR
*"     VALUE(IV_WERKS) TYPE  ZDEMO_STOCK-WERKS
*"  EXPORTING
*"     VALUE(EV_QUANTITY) TYPE  ZDEMO_QUANTITY
*"----------------------------------------------------------------------
  gv_call_count = gv_call_count + 1.

  SELECT SINGLE quantity
    FROM zdemo_stock
    WHERE matnr = @iv_matnr
      AND werks = @iv_werks
    INTO @ev_quantity.
  IF sy-subrc <> 0.
    CLEAR ev_quantity.
  ENDIF.
ENDFUNCTION.
