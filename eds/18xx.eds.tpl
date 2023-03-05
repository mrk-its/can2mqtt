[180${TPDO}]
ParameterName=Transmit PDO 0 communication parameters
ObjectType=9
SubNumber=3

[180${TPDO}sub0]
ParameterName=Number of Entries
ObjectType=7
DataType=5
AccessType=ro
PDOMapping=0
DefaultValue=2
LowLimit=2
HighLimit=2

[180${TPDO}sub1]
ParameterName=COB-ID use by TPDO ${TPDO}
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=\$NODEID+384

[180${TPDO}sub2]
ParameterName=Transmission type TPDO ${TPDO}
ObjectType=7
DataType=5
AccessType=RW
PDOMapping=0
DefaultValue=255
LowLimit=0
HighLimit=255
