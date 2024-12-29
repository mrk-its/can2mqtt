DIR=$(dirname $0)
EDSFILE=$DIR/esphome.eds

(cat $DIR/header.eds.tpl; echo) > $EDSFILE

for TPDO in `seq 0 7`; do
  TPDO=$TPDO envsubst < $DIR/tpdo.eds.tpl ;
  echo
done >> $EDSFILE

(cat $DIR/entity_header.eds.tpl; echo) >> $EDSFILE
