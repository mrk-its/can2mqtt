DIR=$(dirname $0)
EDSFILE=$DIR/esphome.eds

(cat $DIR/header.eds.tpl; echo) > $EDSFILE

(cat $DIR/entity_header.eds.tpl; echo) >> $EDSFILE
