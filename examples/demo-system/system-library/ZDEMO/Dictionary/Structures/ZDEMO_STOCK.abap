@EndUserText.label : 'Demo stock by material/plant (synthetic)'
@AbapCatalog.enhancementCategory : #NOT_EXTENSIBLE
@AbapCatalog.tableCategory : #TRANSPARENT
@AbapCatalog.deliveryClass : #A
@AbapCatalog.dataMaintenance : #RESTRICTED
define table zdemo_stock {
  key client   : abap.clnt not null;
  key matnr    : abap.char(18) not null;
  key werks    : abap.char(4) not null;
  key lgort    : abap.char(4) not null;
  quantity     : zdemo_quantity;
  last_movement : abap.dats;
}
