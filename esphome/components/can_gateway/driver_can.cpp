#include "can_gateway.h"
#include "driver_can.h"



// static CAN_HandleTypeDef DrvCan1;

/******************************************************************************
* PRIVATE FUNCTIONS
******************************************************************************/
namespace esphome {

extern can_gateway::CanGatewayComponent *global_can_gateway;

const char *TAG = "can_driver";
const char *TAG_TM = "timer_driver";

struct timeval timer = {0, 0};

static void DrvCanInit(void) {
    ESP_LOGI(TAG, "DrvCanInit");
}

static void DrvCanEnable(uint32_t baudrate) {
    ESP_LOGI(TAG, "DrvCanEnable baudrate: %d", baudrate);
}

static int16_t DrvCanSend(CO_IF_FRM *frm) {
    if(global_can_gateway && global_can_gateway->canbus) {
        auto len = frm->DLC;
        std::vector<uint8_t> data(frm->Data, frm->Data + len);
        char data_str[3*8 + 1] = "";
        for(int i=0; i<data.size(); i++) {
            sprintf(data_str + i*3, " %02x", data[i]);
        }
        ESP_LOGV(TAG, "DrvCanSend id: %03x, len: %d, data:%s", frm->Identifier, data.size(), data_str);
        global_can_gateway->canbus->send_data(frm->Identifier, false, data);
        return 0;
    } else {
        return -1;
    }
}

static int16_t DrvCanRead (CO_IF_FRM *frm) {
    if(global_can_gateway->recv_frame.has_value()) {
        *frm = global_can_gateway->recv_frame.value();
        global_can_gateway->recv_frame.reset();
        ESP_LOGV(TAG, "DrvCanRead: frame read");
        return sizeof(CO_IF_FRM);
    } else {
        ESP_LOGW(TAG, "DrvCanRead: no frame");
    }
    return 0;
}

static void DrvCanReset(void) {
    ESP_LOGI(TAG, "DrvCanReset");
}

static void DrvCanClose(void) {
    ESP_LOGI(TAG, "DrvCanClose");
}

/******************************************************************************
* PRIVATE FUNCTIONS
******************************************************************************/

static void DrvTimerInit(uint32_t freq) {
    ESP_LOGV(TAG_TM, "DrvTimerInit, freq: %d", freq);
}

static void DrvTimerStart(void) {
    ESP_LOGV(TAG_TM, "DrvTimerStart");
    /* start the hardware timer counting */
}

static uint8_t DrvTimerUpdate(void) {
    if(!timer.tv_sec && !timer.tv_usec) {
        // timer is stopped
        return 0;
    }

    struct timeval tv_now;
    gettimeofday(&tv_now, NULL);

    int32_t dt = (timer.tv_sec - tv_now.tv_sec) * 1000000 + (timer.tv_usec - tv_now.tv_usec);
    ESP_LOGV(TAG_TM, "DrvTimerUpdate %d", dt);
    return dt > 0 ? 0 : 1;
}

static uint32_t DrvTimerDelay(void) {
    struct timeval tv_now;
    gettimeofday(&tv_now, NULL);

    int32_t dt = (timer.tv_sec - tv_now.tv_sec) * 1000000 + (timer.tv_usec - tv_now.tv_usec);
    ESP_LOGV(TAG_TM, "DrvTimerDelay: %d", dt);

    /* return remaining ticks until interrupt occurs */
    return (uint32_t)dt;
}

static void DrvTimerReload(uint32_t reload) {
    /* configure the next hardware timer interrupt */
    ESP_LOGV(TAG_TM, "DrvTimerReload %d", reload);

    gettimeofday(&timer, NULL);
    timer.tv_usec += reload;
}

static void DrvTimerStop(void) {
    ESP_LOGV(TAG_TM, "DrvTimerStop");
    timer.tv_sec = timer.tv_usec = 0;
    /* stop the hardware timer counting */
}

static void DrvNvmInit(void) {
    ESP_LOGI(TAG, "DrvNvmInit");
}

static uint32_t DrvNvmRead(uint32_t start, uint8_t *buffer, uint32_t size)
{
    return 0;
}

static uint32_t DrvNvmWrite(uint32_t start, uint8_t *buffer, uint32_t size) {
    return 0;
}


/******************************************************************************
* PUBLIC VARIABLE
******************************************************************************/

const CO_IF_CAN_DRV ESPHome_CanDriver = {
    DrvCanInit,
    DrvCanEnable,
    DrvCanRead,
    DrvCanSend,
    DrvCanReset,
    DrvCanClose
};

const CO_IF_TIMER_DRV ESPHome_TimerDriver = {
    DrvTimerInit,
    DrvTimerReload,
    DrvTimerDelay,
    DrvTimerStop,
    DrvTimerStart,
    DrvTimerUpdate
};

const CO_IF_NVM_DRV ESPHome_NvmDriver = {
    DrvNvmInit,
    DrvNvmRead,
    DrvNvmWrite
};

}

struct CO_IF_DRV_T ESPHome_CanOpenStack_Driver = {
    &esphome::ESPHome_CanDriver,
    &esphome::ESPHome_TimerDriver,
    &esphome::ESPHome_NvmDriver
};
