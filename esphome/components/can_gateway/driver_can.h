#ifndef DRV_CAN_CAN1_H_
#define DRV_CAN_CAN1_H_

#ifdef __cplusplus               /* for compatibility with C++ environments  */
extern "C" {
#endif

/******************************************************************************
* INCLUDES
******************************************************************************/

#include "co_if.h"

/******************************************************************************
* PUBLIC SYMBOLS
******************************************************************************/

extern const CO_IF_CAN_DRV ESPHome_CanDriver;
extern struct CO_IF_DRV_T ESPHome_CanOpenStack_Driver;

#ifdef __cplusplus               /* for compatibility with C++ environments  */
}
#endif

#endif