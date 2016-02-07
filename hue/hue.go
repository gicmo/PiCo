package hue

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"strings"
)

type Bridge struct {
	Address  string
	Username string
}

func (bridge *Bridge) IsOn(group int) (bool, error) {
	client := &http.Client{}

	url := fmt.Sprintf("http://%s/api/%s/groups/%d", bridge.Address, bridge.Username, group)

	res, err := client.Get(url)
	if err != nil {
		return false, err
	}

	defer res.Body.Close()
	body, err := ioutil.ReadAll(res.Body)

	if err != nil {
		return false, err
	}

	var dict map[string]interface{}

	if err = json.Unmarshal(body, &dict); err != nil {
		return false, err
	}

	on := dict["action"].(map[string]interface{})["on"].(bool)
	return on, nil
}

func (bridge *Bridge) GroupAction(id int, action string) error {
	client := &http.Client{}

	url := fmt.Sprintf("http://%s/api/%s/groups/%d/action", bridge.Address, bridge.Username, id)

	data := strings.NewReader(action)
	req, err := http.NewRequest("PUT", url, data)
	if err != nil {
		return err
	}
	req.ContentLength = int64(data.Len())
	req.Header.Add("Content-Type", "application/json")
	res, err := client.Do(req)
	if err != nil {
		return err
	}
	defer res.Body.Close()
	body, err := ioutil.ReadAll(res.Body)
	if err != nil {
		return err
	}

	var dict map[string]interface{}

	if err = json.Unmarshal(body, &dict); err != nil {
		return err
	}

	if _, ok := dict["success"]; ok {
		return nil
	}

	val := dict["error"].(map[string]interface{})["description"]
	err = fmt.Errorf("hue: %s", val)
	return err
}

func (bridge *Bridge) SetOn(group int, state bool) error {
	return bridge.GroupAction(group, fmt.Sprintf("{\"on\": %v}", state))
}

func (bridge *Bridge) SetScene(group int, scene string) error {
	return bridge.GroupAction(group, fmt.Sprintf("{\"scene\":%q}", scene))
}

type Client struct {
	Bridge   Bridge
	OnAction string
	Group    int
}

func ReadConfig(filename string) (cfg Client, err error) {
	data, err := ioutil.ReadFile(filename)
	if err != nil {
		return
	}
	err = json.Unmarshal(data, &cfg)
	return
}

func (client *Client) Toggle() error {
	bridge := client.Bridge

	state, err := bridge.IsOn(1)
	if err != nil {
		return err
	}

	if state == true {
		return bridge.SetOn(0, false)
	}

	// we are off, have to switch it on
	if client.OnAction == "on" {
		err = bridge.SetOn(client.Group, true)
	} else {
		err = bridge.SetScene(client.Group, client.OnAction)
	}

	return err
}
