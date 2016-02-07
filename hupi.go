package main

import (
	"fmt"
	"time"

	"os"
	"os/signal"
	"syscall"

	"github.com/kidoman/embd"
	_ "github.com/kidoman/embd/host/rpi"

	"github.com/gicmo/PiCo/hue"
)


func main() {
	fmt.Println("PiCo")

	client, err := hue.ReadConfig("/etc/pico")
	if err != nil {
		panic(err)
	}

	sigch := make(chan os.Signal, 2)
	signal.Notify(sigch, os.Interrupt, syscall.SIGTERM)

	if err = embd.InitGPIO(); err != nil {
		panic(err)
	}

	defer embd.CloseGPIO()

	pin18, err := embd.NewDigitalPin(18)
	defer pin18.Close()

	if err != nil {
		panic(err)
	}

	pin18.SetDirection(embd.Out)

	btn, err := embd.NewDigitalPin(24)
	if err != nil {
		panic(err)
	}
	defer btn.Close()

	btn.SetDirection(embd.In)
	btn.ActiveLow(false)

	pressed := make(chan time.Time, 2)
	err = btn.Watch(embd.EdgeBoth, func(btn embd.DigitalPin) {
		pressed <- time.Now()
	})

	bs, _ := btn.Read()
	fmt.Printf("[D] Button state: %v\n", bs)

	onoff := embd.High
	pin18.Write(onoff)

	last_button := time.Unix(0, 0)
	ctchan := make(chan error, 2)
	bc := make(chan int, 1)
	busy := false

loop:
	for {
		select {
		case pressed_time := <-pressed:
			bs, _ = btn.Read()
			fmt.Printf("[D] B: %v\n", bs)
			duration := pressed_time.Sub(last_button)
			if !busy && duration > 500*time.Millisecond {
				fmt.Printf("[D] Key pressed [starting timer]\n")
				last_button = pressed_time
				busy = true
				pin18.Write(embd.Low)

				time.AfterFunc(200*time.Millisecond, func() {
					if state, berr := btn.Read(); berr != nil {
						fmt.Printf("[E] Button read error\n")
						bc <- 0
					} else {
						bc <- state
					}
				})
			}

		case bstate := <-bc:
			fmt.Printf("[D] Timer report: %v\n", bstate)
			if bstate != 0 {
				go func(clt *hue.Client, ch chan error) {
					herr := client.Toggle()
					ch <- herr
				}(&client, ctchan)
			}

		case sig := <-sigch:
			fmt.Println("[I] Got signal", sig)
			break loop

		case err = <-ctchan:
			if err != nil {
				fmt.Printf("[W] toggle: %v", err)
			}
			busy = false
			pin18.Write(embd.High)
		}
	}
}
