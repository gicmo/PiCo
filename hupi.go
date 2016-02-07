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
	err = btn.Watch(embd.EdgeFalling, func(btn embd.DigitalPin) {
		pressed <- time.Now()
	})

	onoff := embd.High
	pin18.Write(onoff)

	last_button := time.Unix(0, 0)

	ctchan := make(chan error, 2)

loop:
	for {
		select {
		case pressed_time := <-pressed:
			duration := pressed_time.Sub(last_button)
			if duration > 500*time.Millisecond {
				last_button = pressed_time
				pin18.Write(embd.Low)

				go func(clt *hue.Client, ch chan error) {
					herr := client.Toggle()
					ch <- herr
				}(&client, ctchan)

			}

		case sig := <-sigch:
			fmt.Println("Got signal", sig)
			break loop

		case err = <-ctchan:
			if err != nil {

			}

			pin18.Write(embd.High)
		}
	}
}
