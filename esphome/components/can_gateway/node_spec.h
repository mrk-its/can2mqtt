/******************************************************************************
   Copyright 2020 Embedded Office GmbH & Co. KG
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
******************************************************************************/

#ifndef CLOCK_SPEC_H_
#define CLOCK_SPEC_H_

#ifdef __cplusplus               /* for compatibility with C++ environments  */
extern "C" {
#endif

/******************************************************************************
* INCLUDES
******************************************************************************/

#include "co_core.h"
/******************************************************************************
* PUBLIC DEFINES
******************************************************************************/

/* Specify the EMCY-IDs for the application */
enum EMCY_CODES {
    APP_ERR_ID_EEPROM = 0,

    APP_ERR_ID_NUM            /* number of EMCY error codes in application */
};

/******************************************************************************
* PUBLIC SYMBOLS
******************************************************************************/

extern struct CO_NODE_SPEC_T NodeSpec;
CO_OBJ *ODFind(CO_OBJ *od, uint32_t key);
CO_OBJ * ODAddUpdate(CO_OBJ *od, uint32_t key, const CO_OBJ_TYPE *type, CO_DATA data);

#ifdef __cplusplus               /* for compatibility with C++ environments  */
}
#endif

#endif /* CLOCK_SPEC_H_ */