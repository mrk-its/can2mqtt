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

[1a0${TPDO}]
ParameterName=TPDO${TPDO} mapping parameter
ObjectType=9
SubNumber=5

[1a0${TPDO}sub0]
ParameterName=Number of mapped objects TPDO${TPDO}
ObjectType=7
DataType=5
AccessType=RW
PDOMapping=0
DefaultValue=1
LowLimit=0
HighLimit=16

[1a0${TPDO}sub1]
ParameterName=TPDO${TPDO} mapping information 1
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub2]
ParameterName=TPDO${TPDO} mapping information 2
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub3]
ParameterName=TPDO${TPDO} mapping information 3
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub4]
ParameterName=TPDO${TPDO} mapping information 4
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub5]
ParameterName=TPDO${TPDO} mapping information 5
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub6]
ParameterName=TPDO${TPDO} mapping information 6
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub7]
ParameterName=TPDO${TPDO} mapping information 7
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub8]
ParameterName=TPDO${TPDO} mapping information 8
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub9]
ParameterName=TPDO${TPDO} mapping information 9
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub10]
ParameterName=TPDO${TPDO} mapping information 10
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub11]
ParameterName=TPDO${TPDO} mapping information 11
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub12]
ParameterName=TPDO${TPDO} mapping information 12
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub13]
ParameterName=TPDO${TPDO} mapping information 13
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub14]
ParameterName=TPDO${TPDO} mapping information 14
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub15]
ParameterName=TPDO${TPDO} mapping information 15
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0

[1a0${TPDO}sub16]
ParameterName=TPDO${TPDO} mapping information 16
ObjectType=7
DataType=7
AccessType=RW
PDOMapping=0
DefaultValue=0
