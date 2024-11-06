DIR=$(dirname $0)
EDSFILE=$DIR/esphome.eds

(cat $DIR/header.eds.tpl; echo) > $EDSFILE

for TPDO in `seq 0 7`; do
  TPDO=$TPDO envsubst < $DIR/tpdo.eds.tpl ;
  echo
done >> $EDSFILE

for RPDO in `seq 0 7`; do
  RPDO=$RPDO envsubst < $DIR/rpdo.eds.tpl ;
  echo
done >> $EDSFILE


(cat $DIR/entity_header.eds.tpl; echo) >> $EDSFILE

for entity_id in `seq 1 64`; do
  ENTITY_ID=$(printf '%02x' $entity_id) envsubst < $DIR/entity.eds.tpl;
  echo
done >> $EDSFILE
