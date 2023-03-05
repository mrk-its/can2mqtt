DIR=$(dirname $0)
EDSFILE=$DIR/esphome.eds

(cat $DIR/header.eds.tpl; echo) > $EDSFILE

for TPDO in `seq 0 3`; do
  TPDO=$TPDO envsubst < $DIR/18xx.eds.tpl ;
  echo
done >> $EDSFILE

for TPDO in `seq 0 3`; do
  TPDO=$TPDO envsubst < $DIR/1axx.eds.tpl;
  echo
done >> $EDSFILE

(cat $DIR/entity_header.eds.tpl; echo) >> $EDSFILE

for entity_id in `seq 1 32`; do
  ENTITY_ID=$(printf '%02x' $entity_id) envsubst < $DIR/entity.eds.tpl;
  echo
done >> $EDSFILE
