[DeviceInfo]
VendorName=ESPHome
VendorNumber=1
BaudRate_10=0
BaudRate_20=0
BaudRate_50=0
BaudRate_125=1
BaudRate_250=1
BaudRate_500=1
BaudRate_800=0
BaudRate_1000=1
SimpleBootUpMaster=0
SimpleBootUpSlave=1
Granularity=8
DynamicChannelsSupported=0
CompactPDO=0
GroupMessaging=0

NrOfRXPDO=0
NrOfTXPDO=4
LSS_Supported=0

[1008]
ParameterName=DeviceName
ObjectType=7
DataType=9
AccessType=R

[1009]
ParameterName=HardwareVersion
ObjectType=7
DataType=9
AccessType=R

[100a]
ParameterName=SoftwareVersion
ObjectType=7
DataType=9
AccessType=R

[1010]
ParameterName=ParamStore
ObjectType=9

[1010sub0]
ParameterName=Number of ParamStore Entries
ObjectType=7
DataType=5
AccessType=R

[1010sub1]
ParameterName=Store All
ObjectType=7
DataType=7
AccessType=RW

[1010sub2]
ParameterName=Store Comm
ObjectType=7
DataType=7
AccessType=RW

[1011]
ParameterName=ParamReset
ObjectType=9

[1011sub0]
ParameterName=Number of ParamStore Entries
ObjectType=7
DataType=5
AccessType=R

[1011sub1]
ParameterName=Reset All Params
ObjectType=7
DataType=7
AccessType=RW

[1011sub2]
ParameterName=Reset Comm Params
ObjectType=7
DataType=7
AccessType=RW



[1017]
ParameterName=ProducerHeartbeatTime
ObjectType=7
DataType=6
AccessType=RW

[1018]
ParameterName=Identity
ObjectType=9

[1018sub0]
ParameterName=Number of Entries
ObjectType=7
DataType=5
AccessType=R

[1018sub1]
ParameterName=VendorId
ObjectType=7
DataType=7
AccessType=R

[1018sub2]
ParameterName=ProductCode
ObjectType=7
DataType=7
AccessType=R

[1018sub3]
ParameterName=RevisionNumber
ObjectType=7
DataType=7
AccessType=R

[1018sub4]
ParameterName=SerialNumber
ObjectType=7
DataType=7
AccessType=R
