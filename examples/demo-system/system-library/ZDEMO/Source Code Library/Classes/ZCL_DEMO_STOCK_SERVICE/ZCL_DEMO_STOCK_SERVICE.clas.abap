*"* SYNTHETIC demo (abap_wiki demo-system) - NOT code from a real system.
CLASS zcl_demo_stock_service DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    METHODS get_quantity
      IMPORTING iv_matnr           TYPE zdemo_stock-matnr
                iv_werks           TYPE zdemo_stock-werks
      RETURNING VALUE(rv_quantity) TYPE zdemo_quantity.

  PRIVATE SECTION.
    DATA mv_last_matnr TYPE zdemo_stock-matnr.
ENDCLASS.

CLASS zcl_demo_stock_service IMPLEMENTATION.

  METHOD get_quantity.
    mv_last_matnr = iv_matnr.
    CALL FUNCTION 'ZDEMO_FG_GET_STOCK'
      EXPORTING
        iv_matnr    = iv_matnr
        iv_werks    = iv_werks
      IMPORTING
        ev_quantity = rv_quantity.
  ENDMETHOD.

ENDCLASS.
