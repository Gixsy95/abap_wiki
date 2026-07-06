*&---------------------------------------------------------------------*
*& Include ZDEMO_STOCK_REPORT_TOP - global data of ZDEMO_STOCK_REPORT
*&---------------------------------------------------------------------*
*& SYNTHETIC demo (abap_wiki demo-system) - NOT code from a real system.
*&---------------------------------------------------------------------*

TYPES: BEGIN OF ty_stock,
         matnr    TYPE zdemo_stock-matnr,
         werks    TYPE zdemo_stock-werks,
         lgort    TYPE zdemo_stock-lgort,
         quantity TYPE zdemo_stock-quantity,
         detail   TYPE string,
       END OF ty_stock,
       tt_stock TYPE STANDARD TABLE OF ty_stock WITH DEFAULT KEY.

DATA: gt_stock TYPE tt_stock,
      gs_stock TYPE ty_stock,
      gv_lines TYPE i.
